#!/usr/bin/env python3
"""
generate_brief.py - Generate weekly executive briefs from multiple summaries

This script compiles multiple intelligence summaries into a weekly executive brief
following the standard template format.

Usage:
    python generate_brief.py --summaries summary1.txt summary2.txt summary3.txt
    python generate_brief.py --directory ./summaries/ --week 2026-01-13
    python generate_brief.py --interactive

Requirements:
    - python-docx (optional, for Word document generation)
"""

import argparse
import re
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple


import json
from pathlib import Path

def load_taxonomy(path: str = "taxonomy.json") -> dict:
    """
    Load canonical topics and region rules from taxonomy.json.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))

# Country extraction uses pycountry (installed) and simple word-boundary matching.
try:
    import pycountry
except Exception:
    pycountry = None

def _build_country_patterns():
    patterns = {}
    if pycountry is None:
        return patterns
    names = set()
    for c in list(pycountry.countries):
        for attr in ("name", "official_name", "common_name"):
            v = getattr(c, attr, None)
            if v:
                names.add(v)
        # Include alpha_2/alpha_3? Not helpful in prose, skip.
    # Add common variants
    names.update(["UK", "U.K.", "United States", "U.S.", "USA", "U.S.A.", "Russia", "Czech Republic", "Czechia", "South Korea", "North Korea"])
    # Sort longer first to avoid partial matches
    for name in sorted(names, key=len, reverse=True):
        # escape dots etc; word boundaries with spaces/hyphens handled loosely
        pat = re.compile(r'(?<![A-Za-z])' + re.escape(name) + r'(?![A-Za-z])', re.IGNORECASE)
        patterns[name] = pat
    return patterns

_COUNTRY_PATTERNS = _build_country_patterns()

def extract_country_mentions(text: str) -> list:
    if not text:
        return []
    found = set()
    for name, pat in _COUNTRY_PATTERNS.items():
        if pat.search(text):
            # normalize some aliases
            key = name
            if key.lower() in {"u.s.", "u.s.a.", "usa", "united states"}:
                key = "United States"
            if key.lower() in {"uk", "u.k.", "united kingdom", "britain", "great britain"}:
                key = "United Kingdom"
            found.add(key)
    return sorted(found)

def rollup_regions(text: str, country_mentions: list) -> dict:
    """
    Returns:
      regions_mentioned, regions_relevant_to_apex_mobility
    """
    taxonomy = load_taxonomy()
    footprint = set(taxonomy.get("footprint_regions", []))

    t = (text or "").lower()
    regions_mentioned = set()

    # Broad mentions -> Europe rollup
    europe_terms = {"europe", "eu", "european", "emea", "european union"}
    if any(term in t for term in europe_terms):
        regions_mentioned.add("Europe (including Russia)")

    # Broad mentions -> Africa rollup
    if "africa" in t or "african" in t:
        regions_mentioned.add("Africa")

    # Country-based rollups
    europe_countries = {
        "United Kingdom","Turkey","Russia","France","Germany","Spain","Italy","Czech Republic","Czechia",
        "Poland","Netherlands","Belgium","Sweden","Norway","Finland","Denmark","Austria","Switzerland",
        "Portugal","Greece","Hungary","Romania","Bulgaria","Slovakia","Slovenia","Croatia","Serbia",
        "Ukraine","Ireland","Iceland","Estonia","Latvia","Lithuania"
    }
    africa_countries = {"Morocco","South Africa"}

    for c in country_mentions or []:
        if c in {"India","China","Mexico","Thailand","United States"}:
            # map to footprint region labels
            if c == "United States":
                regions_mentioned.add("US")
            else:
                regions_mentioned.add(c)
        if c in europe_countries:
            regions_mentioned.add("Europe (including Russia)")
        if c in africa_countries:
            regions_mentioned.add("Africa")

    regions_relevant = sorted(set(regions_mentioned).intersection(footprint))
    return {
        "regions_mentioned": sorted(regions_mentioned),
        "regions_relevant_to_apex_mobility": regions_relevant
    }



def enrich_with_region_tags(summary: dict) -> dict:
    """
    Adds country_mentions / regions_mentioned / regions_relevant_to_apex_mobility to the summary dict.
    """
    text_fields = []
    for k in ("title", "summary", "key_developments", "strategic_implications", "raw_text", "content"):
        v = summary.get(k)
        if isinstance(v, str):
            text_fields.append(v)
        elif isinstance(v, list):
            text_fields.extend([x for x in v if isinstance(x, str)])
    joined = "\n".join(text_fields)
    countries = summary.get("country_mentions") or extract_country_mentions(joined)
    summary["country_mentions"] = countries
    region_info = rollup_regions(joined, countries)
    summary.setdefault("regions_mentioned", region_info["regions_mentioned"])
    summary.setdefault("regions_relevant_to_apex_mobility", region_info["regions_relevant_to_apex_mobility"])
    return summary




try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False


class BriefGenerator:
    """Generate weekly executive briefs from intelligence summaries"""
    
    def __init__(self):
        self.summaries = []
        self.high_priority = []
        self.by_topic = defaultdict(list)
        self.companies = Counter()
        self.topics = Counter()
        self.week_start = None
        self.week_end = None
    
    def add_summary(self, summary_data: Dict):
        """Add a summary to the brief"""
        self.summaries.append(summary_data)
        
        # Track metadata
        if summary_data.get("priority") == "High":
            self.high_priority.append(summary_data)
        
        # Group by topic
        for topic in summary_data.get("topics", ["Other"]):
            self.by_topic[topic].append(summary_data)
            self.topics[topic] += 1
        
        # Track companies
        for company in summary_data.get("companies", []):
            self.companies[company] += 1
    
    def parse_summary_file(self, filepath: str) -> Dict:
        """Parse a summary file and extract structured data"""
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        data = {
            "title": self._extract_field(text, "title"),
            "source": self._extract_field(text, "source"),
            "url": self._extract_field(text, "url"),
            "companies": self._extract_list(text, "companies mentioned"),
            "topics": self._extract_list(text, "topics"),
            "priority": self._extract_field(text, "priority") or "Medium",
            "key_developments": self._extract_bullets(text, "key developments"),
            "strategic_implications": self._extract_paragraph(text, "strategic implications"),
        }
        
        return data
    
    def _extract_field(self, text: str, field: str) -> str:
        """Extract a single field value"""
        pattern = rf"{field}:?\s*(.+?)(?:\n|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            value = match.group(1).strip()
            # Remove source date for cleaner extraction
            value = re.sub(r',\s*\d{4}-\d{2}-\d{2}', '', value)
            value = re.sub(r',\s*\w+ \d{1,2},? \d{4}', '', value)
            return value
        
        # For title, try first line
        if field.lower() == "title":
            first_line = text.split('\n')[0].strip()
            # Remove common separators
            first_line = re.sub(r'^[=\-]+\s*', '', first_line)
            first_line = re.sub(r'\s*[=\-]+$', '', first_line)
            return first_line
        
        return ""
    
    def _extract_list(self, text: str, field: str) -> List[str]:
        """Extract a comma-separated list field"""
        pattern = rf"{field}:?\s*(.+?)(?:\n|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        
        if match:
            items = match.group(1).strip()
            return [item.strip() for item in re.split(r'[,;]', items) if item.strip()]
        
        return []
    
    def _extract_bullets(self, text: str, section: str) -> List[str]:
        """Extract bullet points from a section"""
        pattern = rf"{section}:?\s*\n((?:â€¢|•|\*|-|\d+\.)\s*.+(?:\n(?:â€¢|•|\*|-|\d+\.)\s*.+)*)"
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        
        if match:
            bullets_text = match.group(1)
            bullets = re.findall(r"(?:â€¢|•|\*|-|\d+\.)\s*(.+)", bullets_text)
            return [b.strip() for b in bullets if b.strip()]
        
        return []
    
    def _extract_paragraph(self, text: str, section: str) -> str:
        """Extract a paragraph section"""
        pattern = rf"{section}:?\s*\n(.+?)(?:\n\n|\n[A-Z\s]{{3,}}:|\Z)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return match.group(1).strip()
        
        return ""
    
    def set_date_range(self, start_date: str = None, end_date: str = None):
        """Set the week's date range"""
        if start_date:
            self.week_start = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            # Default to last Monday
            today = datetime.now()
            self.week_start = today - timedelta(days=today.weekday())
        
        if end_date:
            self.week_end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            # Sunday of the same week
            self.week_end = self.week_start + timedelta(days=6)
    
    def generate_text_brief(self) -> str:
        """Generate brief in text format"""
        lines = []
        
        # Header
        lines.append("AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF")
        if self.week_start and self.week_end:
            lines.append(f"Week of {self.week_start.strftime('%B %d')} - "
                        f"{self.week_end.strftime('%B %d, %Y')}")
        lines.append("Prepared by: Market Intelligence Agent")
        lines.append("")
        lines.append("=" * 70)
        lines.append("")
        
        # Executive Summary
        lines.append("EXECUTIVE SUMMARY")
        lines.append("")
        lines.append(self._generate_executive_summary())
        lines.append("")
        lines.append(f"Key Metrics: {len(self.summaries)} items tracked | "
                    f"{len(self.high_priority)} high priority | "
                    f"{len(self.companies)} companies mentioned")
        lines.append("")
        lines.append("=" * 70)
        lines.append("")
        
        # High Priority Developments
        if self.high_priority:
            lines.append("HIGH PRIORITY DEVELOPMENTS")
            lines.append("")
            
            for i, summary in enumerate(self.high_priority, 1):
                lines.append(f"{i}. {summary.get('title', 'Untitled')}")
                if summary.get('source'):
                    lines.append(f"   Source: {summary['source']}")
                if summary.get('key_developments'):
                    lines.append("   • " + summary['key_developments'][0])
                if summary.get('strategic_implications'):
                    impl = summary['strategic_implications'][:200] + "..." if len(summary['strategic_implications']) > 200 else summary['strategic_implications']
                    lines.append(f"   Strategic Implication: {impl}")
                if summary.get('url'):
                    lines.append(f"   Link: {summary['url']}")
                lines.append("")
            
            lines.append("=" * 70)
            lines.append("")
        
        # Key Developments by Topic
        lines.append("KEY DEVELOPMENTS BY TOPIC")
        lines.append("")
        
        # Sort topics by frequency
        sorted_topics = sorted(self.topics.items(), key=lambda x: x[1], reverse=True)
        
        for topic, count in sorted_topics[:5]:  # Top 5 topics
            emoji = self._get_topic_marker(topic)
            lines.append(f"{emoji} {topic.upper()} ({count} items)")
            lines.append("")
            
            for summary in self.by_topic[topic][:5]:  # Top 5 items per topic
                companies = ", ".join(summary.get("companies", ["Unknown"])[:2])
                title = summary.get("title", "Untitled")
                # Shorten title if needed
                if len(title) > 80:
                    title = title[:77] + "..."
                lines.append(f"• {companies} - {title}")
            
            lines.append("")
        
        lines.append("=" * 70)
        lines.append("")
        
        # Emerging Trends
        lines.append("EMERGING TRENDS")
        lines.append("")
        trends = self._identify_trends()
        for i, (trend_name, trend_data) in enumerate(trends, 1):
            lines.append(f"Trend {i}: {trend_name}")
            lines.append(f"• Evidence: {len(trend_data['supporting_items'])} related items")
            lines.append(f"• Key players: {', '.join(trend_data['companies'][:5])}")
            lines.append(f"• Significance: {trend_data['significance']}")
            lines.append("")
        
        lines.append("=" * 70)
        lines.append("")
        
        # Recommended Actions
        lines.append("RECOMMENDED ACTIONS")
        lines.append("")
        actions = self._generate_recommendations()
        for i, action in enumerate(actions, 1):
            lines.append(f"{i}. {action}")
        lines.append("")
        
        lines.append("=" * 70)
        lines.append("")
        
        # Statistics Footer
        lines.append("Report Details:")
        lines.append(f"Total Items Processed: {len(self.summaries)}")
        lines.append(f"High Priority: {len(self.high_priority)}")
        lines.append(f"Medium Priority: {len([s for s in self.summaries if s.get('priority') == 'Medium'])}")
        lines.append(f"Low Priority: {len([s for s in self.summaries if s.get('priority') == 'Low'])}")
        lines.append("")
        top_companies = self.companies.most_common(10)
        lines.append(f"Companies Mentioned: {', '.join([c for c, _ in top_companies])}")
        lines.append(f"Topics Covered: {', '.join([t for t, _ in sorted_topics])}")
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def _generate_executive_summary(self) -> str:
        """Generate executive summary from summaries"""
        # This is a simplified version; in production, this could use LLM
        high_pri_count = len(self.high_priority)
        
        if high_pri_count == 0:
            summary = "This week saw continued activity across multiple automotive sectors with no critical high-priority developments."
        elif high_pri_count == 1:
            summary = f"This week featured one critical development: {self.high_priority[0].get('title', 'key announcement')}."
        else:
            summary = f"This week included {high_pri_count} high-priority developments, notably "
            summary += f"{self.high_priority[0].get('title', 'announcement')} and "
            summary += f"{self.high_priority[1].get('title', 'announcement')}."
        
        # Add top topic
        if self.topics:
            top_topic = self.topics.most_common(1)[0][0]
            summary += f" {top_topic} was the most active area with {self.topics[top_topic]} developments."
        
        return summary
    
    def _get_topic_marker(self, topic: str) -> str:
        taxonomy = load_taxonomy()
        markers = taxonomy.get("topic_markers", {})
        return markers.get(topic, "-")
    
    def _identify_trends(self) -> List[Tuple[str, Dict]]:
        """Identify emerging trends from summaries"""
        # Simplified trend identification
        trends = []
        
        # Check for recurring themes
        all_titles = " ".join([s.get("title", "") for s in self.summaries]).lower()
        
        # Battery technology trends
        if "solid-state" in all_titles or "solid state" in all_titles:
            related = [s for s in self.summaries if "solid" in s.get("title", "").lower()]
            if len(related) >= 2:
                trends.append((
                    "Solid-State Battery Acceleration",
                    {
                        "supporting_items": related,
                        "companies": list(set([c for s in related for c in s.get("companies", [])])),
                        "significance": "Multiple companies advancing solid-state timelines suggests technology maturation"
                    }
                ))
        
        # Partnership trends
        partnership_items = self.by_topic.get("Partnerships", [])
        if len(partnership_items) >= 3:
            trends.append((
                "Increased Partnership Activity",
                {
                    "supporting_items": partnership_items,
                    "companies": list(set([c for s in partnership_items for c in s.get("companies", [])])),
                    "significance": "High volume of partnerships indicates supply chain restructuring and strategic repositioning"
                }
            ))
        
        return trends
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on brief content"""
        recommendations = []
        
        # High priority item follow-ups
        if self.high_priority:
            top_companies = list(set([c for s in self.high_priority for c in s.get("companies", [])]))[:3]
            recommendations.append(
                f"Monitor {', '.join(top_companies)} closely for follow-up announcements "
                "and strategic responses (Timeline: Next 2 weeks)"
            )
        
        # Topic-based recommendations
        if self.topics.most_common(1):
            top_topic = self.topics.most_common(1)[0][0]
            recommendations.append(
                f"Conduct deeper analysis of {top_topic} trends and competitive implications "
                "(Timeline: This week)"
            )
        
        # Partner/competitor intelligence
        top_companies = self.companies.most_common(5)
        if len(top_companies) >= 3:
            recommendations.append(
                f"Review strategic positioning vs. {top_companies[0][0]}, {top_companies[1][0]}, "
                f"and {top_companies[2][0]} (Timeline: End of month)"
            )
        
        return recommendations


def main():
    parser = argparse.ArgumentParser(
        description="Generate weekly automotive market intelligence briefs"
    )
    parser.add_argument(
        "--summaries",
        "-s",
        nargs="+",
        help="Summary files to include in brief"
    )
    parser.add_argument(
        "--directory",
        "-d",
        help="Directory containing summary files"
    )
    parser.add_argument(
        "--week",
        "-w",
        help="Week start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path"
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["txt", "docx"],
        default="txt",
        help="Output format"
    )
    
    args = parser.parse_args()
    
    generator = BriefGenerator()
    
    # Set date range
    if args.week:
        generator.set_date_range(start_date=args.week)
    else:
        generator.set_date_range()  # Use current week
    
    # Collect summary files
    summary_files = []
    
    if args.summaries:
        summary_files = args.summaries
    elif args.directory:
        dir_path = Path(args.directory)
        if not dir_path.exists():
            print(f"Error: Directory '{args.directory}' not found.")
            return
        summary_files = list(dir_path.glob("*.txt")) + list(dir_path.glob("*.md"))
    else:
        print("Error: Must specify --summaries or --directory")
        return
    
    if not summary_files:
        print("Error: No summary files found.")
        return
    
    print(f"Processing {len(summary_files)} summaries...")
    
    # Parse and add summaries
    for filepath in summary_files:
        try:
            summary_data = generator.parse_summary_file(str(filepath))
            generator.add_summary(summary_data)
        except Exception as e:
            print(f"Warning: Failed to parse {filepath}: {e}")
    
    # Generate brief
    print("Generating brief...")
    brief_text = generator.generate_text_brief()
    
    # Output
    if args.output:
        output_path = Path(args.output)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(brief_text)
        print(f"\nBrief saved to: {output_path}")
    else:
        print("\n" + brief_text)


if __name__ == "__main__":
    main()
