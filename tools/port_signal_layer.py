#!/usr/bin/env python3
"""Port Signal Layer and Accountability Layer nodes to Square-Two schema.

Migrates:
- 11 Signal Layer nodes (independent media, government officials, crowd intel)
- 8 Accountability Layer nodes (crime/fraud events)
- Associated edges linking them to the thesis

Run: python3 tools/port_signal_layer.py
"""

import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fgip.db import FGIPDatabase
from fgip.schema import NodeType, EdgeType


# Signal Layer Nodes (11 total)
SIGNAL_NODES = [
    {
        "node_id": "media-shawn-ryan-show",
        "node_type": "MEDIA_OUTLET",
        "name": "Shawn Ryan Show",
        "metadata": {
            "platform": "youtube",
            "host": "Shawn Ryan",
            "signal_type": "independent_media",
            "topics_covered": ["defense_industrial_base", "intelligence_gaps", "fentanyl", "china_threat"],
            "url": "https://youtube.com/@ShawnRyanShow"
        }
    },
    {
        "node_id": "person-sarah-adams",
        "node_type": "PERSON",
        "name": "Sarah Adams",
        "metadata": {
            "role": "CIA targeter",
            "signal_type": "whistleblower",
            "appeared_on": "media-shawn-ryan-show",
            "topics_covered": ["intelligence_gaps", "china_threat"]
        }
    },
    {
        "node_id": "media-tucker-carlson",
        "node_type": "MEDIA_OUTLET",
        "name": "Tucker Carlson Network",
        "metadata": {
            "platform": "youtube/x",
            "signal_type": "independent_media",
            "topics_covered": ["institutional_capture", "immigration", "foreign_influence"]
        }
    },
    {
        "node_id": "media-joe-rogan",
        "node_type": "MEDIA_OUTLET",
        "name": "Joe Rogan Experience",
        "metadata": {
            "platform": "spotify/youtube",
            "signal_type": "independent_media",
            "topics_covered": ["censorship", "institutional_capture", "tech_policy"]
        }
    },
    {
        "node_id": "media-breaking-points",
        "node_type": "MEDIA_OUTLET",
        "name": "Breaking Points",
        "metadata": {
            "platform": "youtube",
            "hosts": ["Krystal Ball", "Saagar Enjeti"],
            "signal_type": "independent_media",
            "topics_covered": ["populist_economics", "reshoring", "institutional_failure"]
        }
    },
    {
        "node_id": "media-all-in-podcast",
        "node_type": "MEDIA_OUTLET",
        "name": "All-In Podcast",
        "metadata": {
            "platform": "youtube",
            "hosts": ["Chamath Palihapitiya", "Jason Calacanis", "David Sacks", "David Friedberg"],
            "signal_type": "independent_media",
            "topics_covered": ["macro_economics", "tariffs", "reshoring", "tech_policy"]
        }
    },
    {
        "node_id": "media-palantir-luckey",
        "node_type": "MEDIA_OUTLET",
        "name": "Palantir / Palmer Luckey Public Statements",
        "metadata": {
            "signal_type": "industry_insider",
            "topics_covered": ["defense_industrial_base", "supply_chain", "china_threat"]
        }
    },
    {
        "node_id": "person-marco-rubio",
        "node_type": "PERSON",
        "name": "Marco Rubio",
        "metadata": {
            "position": "Secretary of State",
            "signal_type": "government_official",
            "topics_covered": ["reshoring", "china_threat", "critical_minerals", "economic_sovereignty"]
        }
    },
    {
        "node_id": "media-substack-ecosystem",
        "node_type": "MEDIA_OUTLET",
        "name": "Substack Independent Journalism Ecosystem",
        "metadata": {
            "platform": "substack",
            "signal_type": "independent_media",
            "key_writers": [
                "manufacturingtalks - industrial decline",
                "urbanomics - chronicle of industrial decline",
                "profstevekeen - Ricardo deception",
                "libertyordeath101 - 50-year plot against American worker",
                "adastraperaspera - US industrial policy revival",
                "freemarketfuturist - free market industrial policy"
            ],
            "topics_covered": ["industrial_decline", "reshoring", "economic_policy"]
        }
    },
    {
        "node_id": "media-reddit-wsb",
        "node_type": "MEDIA_OUTLET",
        "name": "r/wallstreetbets",
        "metadata": {
            "platform": "reddit",
            "signal_type": "crowd_intelligence",
            "members": 15000000,
            "topics_covered": ["retail_investing", "great_rotation", "reshoring_etfs"]
        }
    },
    {
        "node_id": "media-reddit-manufacturing",
        "node_type": "MEDIA_OUTLET",
        "name": "Manufacturing/Reshoring Reddit Communities",
        "metadata": {
            "platform": "reddit",
            "signal_type": "crowd_intelligence",
            "topics_covered": ["factory_openings", "hiring", "supply_chain"]
        }
    },
]

# Accountability Layer Nodes (8 total)
ACCOUNTABILITY_NODES = [
    {
        "node_id": "crime-feeding-our-future",
        "node_type": "ECONOMIC_EVENT",
        "name": "Feeding Our Future Fraud (Minnesota)",
        "metadata": {
            "crime_type": "fraud",
            "location": "Minnesota",
            "amount_stolen": 250000000,
            "defendants": 70,
            "status": "prosecutions ongoing",
            "source_urls": [
                "https://en.wikipedia.org/wiki/Feeding_Our_Future",
                "https://www.cbsnews.com/news/minnesota-fraud-schemes-what-we-know/"
            ]
        }
    },
    {
        "node_id": "crime-minnesota-daycare",
        "node_type": "ECONOMIC_EVENT",
        "name": "Minnesota Daycare Fraud Schemes",
        "metadata": {
            "crime_type": "fraud",
            "location": "Minnesota",
            "status": "prosecutions ongoing"
        }
    },
    {
        "node_id": "crime-hsbc-laundering",
        "node_type": "ECONOMIC_EVENT",
        "name": "HSBC Money Laundering ($1.92B Fine)",
        "metadata": {
            "crime_type": "money_laundering",
            "fine": 1920000000,
            "iran_hidden": 19400000000,
            "executives_imprisoned": 0,
            "year": 2012,
            "source_url": "https://en.wikipedia.org/wiki/HSBC"
        }
    },
    {
        "node_id": "crime-fentanyl-pipeline",
        "node_type": "ECONOMIC_EVENT",
        "name": "Fentanyl Precursor Pipeline (China → US)",
        "metadata": {
            "crime_type": "narcotics_trafficking",
            "deaths_per_year": 100000,
            "precursor_source": "China",
            "enabled_by": "pntr-2000",
            "source_urls": [
                "https://www.brookings.edu/articles/the-fentanyl-pipeline-and-chinas-role-in-the-us-opioid-crisis/",
                "https://www.state.gov/wp-content/uploads/2025/09/Tab-1-Mandatory-Congressional-Report-on-China-Narcotics-Accessible-9.17.2025.pdf"
            ]
        }
    },
    {
        "node_id": "crime-forced-labor-xinjiang",
        "node_type": "ECONOMIC_EVENT",
        "name": "Xinjiang Forced Labor (Uyghur)",
        "metadata": {
            "crime_type": "human_rights_abuse",
            "legislation_response": "UFLPA",
            "source_url": "https://www.cfr.org/blog/chinas-use-forced-labor-xinjiang-wake-call-heard-round-world"
        }
    },
    {
        "node_id": "crime-censorship-infrastructure",
        "node_type": "ECONOMIC_EVENT",
        "name": "Government Censorship Infrastructure (2021-2024)",
        "metadata": {
            "crime_type": "government_overreach",
            "investigating_body": "House Judiciary Committee",
            "source_urls": [
                "https://judiciary.house.gov/sites/evo-subsites/republicans-judiciary.house.gov/files/evo-media-document/Biden-WH-Censorship-Report-final.pdf"
            ]
        }
    },
    {
        "node_id": "crime-haugen-coordination",
        "node_type": "ECONOMIC_EVENT",
        "name": "Frances Haugen Testimony Coordination",
        "metadata": {
            "crime_type": "coordinated_narrative",
            "date": "2021-10",
            "source_urls": [
                "https://en.wikipedia.org/wiki/Frances_Haugen",
                "https://www.npr.org/2021/10/05/1043377310/facebook-whistleblower-frances-haugen-congress"
            ]
        }
    },
    {
        "node_id": "crime-refugee-resettlement-fraud",
        "node_type": "ECONOMIC_EVENT",
        "name": "Refugee Resettlement Industry Fraud",
        "metadata": {
            "crime_type": "fraud",
            "source_urls": [
                "https://capitalresearch.org/article/refugee-resettlement-the-lucrative-business-of-serving-immigrants"
            ]
        }
    },
]


def port_signal_layer(db_path: str = "fgip.db"):
    """Port all signal and accountability nodes to Square-Two schema."""
    import hashlib

    db = FGIPDatabase(db_path)
    conn = db.connect()

    nodes_created = 0
    sources_created = 0

    print("=== Porting Signal Layer (11 nodes) ===\n")
    for node in SIGNAL_NODES:
        try:
            # Generate sha256 from node content
            content = json.dumps(node, sort_keys=True)
            sha256 = hashlib.sha256(content.encode()).hexdigest()

            conn.execute("""
                INSERT OR IGNORE INTO nodes (node_id, name, node_type, metadata, created_at, sha256)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            """, (
                node["node_id"],
                node["name"],
                node["node_type"],
                json.dumps(node.get("metadata", {})),
                sha256
            ))
            conn.commit()
            # Check if it was inserted
            exists = conn.execute("SELECT 1 FROM nodes WHERE node_id = ?", (node["node_id"],)).fetchone()
            if exists:
                nodes_created += 1
                print(f"  ✓ {node['name']} ({node['node_type']})")
        except Exception as e:
            print(f"  ✗ {node['name']}: {e}")

    print(f"\n=== Porting Accountability Layer (8 nodes) ===\n")

    for node in ACCOUNTABILITY_NODES:
        try:
            # Generate sha256 from node content
            content = json.dumps(node, sort_keys=True)
            sha256 = hashlib.sha256(content.encode()).hexdigest()

            conn.execute("""
                INSERT OR IGNORE INTO nodes (node_id, name, node_type, metadata, created_at, sha256)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
            """, (
                node["node_id"],
                node["name"],
                node["node_type"],
                json.dumps(node.get("metadata", {})),
                sha256
            ))
            conn.commit()
            # Check if it was inserted
            exists = conn.execute("SELECT 1 FROM nodes WHERE node_id = ?", (node["node_id"],)).fetchone()
            if exists:
                nodes_created += 1
                print(f"  ✓ {node['name']}")

            # Add sources from metadata
            metadata = node.get("metadata", {})
            source_urls = metadata.get("source_urls", [])
            if metadata.get("source_url"):
                source_urls.append(metadata["source_url"])

            for url in source_urls:
                # Auto-tier based on domain
                from fgip.schema import extract_domain, auto_tier_domain
                domain = extract_domain(url)
                tier = auto_tier_domain(domain)

                source_id = f"src-{hash(url) % 1000000:06d}"
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at)
                        VALUES (?, ?, ?, ?, datetime('now'))
                    """, (source_id, url, domain, tier))
                    sources_created += 1
                except:
                    pass

        except Exception as e:
            print(f"  ✗ {node['name']}: {e}")

    conn.commit()

    print(f"\n=== Summary ===")
    print(f"Nodes created: {nodes_created}")
    print(f"Sources created: {sources_created}")

    # Verify
    signal_count = conn.execute("""
        SELECT COUNT(*) FROM nodes WHERE metadata LIKE '%signal_type%'
    """).fetchone()[0]

    crime_count = conn.execute("""
        SELECT COUNT(*) FROM nodes WHERE node_id LIKE 'crime-%'
    """).fetchone()[0]

    print(f"\nSignal nodes in DB: {signal_count}")
    print(f"Crime nodes in DB: {crime_count}")

    return nodes_created, sources_created


if __name__ == "__main__":
    port_signal_layer()
