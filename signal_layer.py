"""
FGIP Signal Layer - Independent media and accountability nodes/edges.

Adds:
1. Signal Layer - Independent media sources validating the thesis
2. Accountability Layer - Documented crime/fraud connected to causality chain
"""

import json
import sqlite3
from typing import Dict, List, Tuple

from schema import source_id_from_url, get_domain, get_tier


# Signal Layer Nodes
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

# Accountability Layer Nodes (Crime/Fraud)
ACCOUNTABILITY_NODES = [
    {
        "node_id": "crime-feeding-our-future",
        "node_type": "ECONOMIC_EVENT",
        "name": "Feeding Our Future Fraud (Minnesota)",
        "metadata": {
            "type": "fraud",
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
            "type": "fraud",
            "location": "Minnesota",
            "status": "prosecutions ongoing"
        }
    },
    {
        "node_id": "crime-hsbc-laundering",
        "node_type": "ECONOMIC_EVENT",
        "name": "HSBC Money Laundering ($1.92B Fine)",
        "metadata": {
            "type": "money_laundering",
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
            "type": "narcotics_trafficking",
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
            "type": "human_rights_abuse",
            "legislation_response": "UFLPA",
            "source_url": "https://www.cfr.org/blog/chinas-use-forced-labor-xinjiang-wake-call-heard-round-world"
        }
    },
    {
        "node_id": "crime-censorship-infrastructure",
        "node_type": "ECONOMIC_EVENT",
        "name": "Government Censorship Infrastructure (2021-2024)",
        "metadata": {
            "type": "government_overreach",
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
            "type": "coordinated_narrative",
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
            "type": "fraud",
            "source_urls": [
                "https://capitalresearch.org/article/refugee-resettlement-the-lucrative-business-of-serving-immigrants"
            ]
        }
    },
]

# New edge types
NEW_EDGE_TYPES = [
    "REPORTS_ON",      # Media/person covers a topic or entity
    "VALIDATES",       # Independent source confirms a claim
    "ENABLED",         # Policy/legislation enabled a crime/fraud
    "PROFITED_FROM",   # Entity profited from crime/harmful activity
    "INVESTIGATED",    # Body investigated a crime/entity
    "COORDINATED_WITH", # Entities coordinated actions
]

# Signal/Accountability Edges
SIGNAL_EDGES = [
    # Independent media reports on thesis elements
    {
        "from_node": "media-shawn-ryan-show",
        "to_node": "crime-fentanyl-pipeline",
        "relationship": "REPORTS_ON",
        "detail": "Multiple episodes covering fentanyl crisis, China precursors, intelligence gaps",
        "confidence": "high",
    },
    {
        "from_node": "media-shawn-ryan-show",
        "to_node": "pntr-2000",
        "relationship": "REPORTS_ON",
        "detail": "Defense industrial base collapse coverage traces to PNTR/offshoring",
        "confidence": "high",
    },
    {
        "from_node": "person-marco-rubio",
        "to_node": "reshoring-2025",
        "relationship": "VALIDATES",
        "detail": "Munich Security Conference Feb 2026: America must direct economy to counter China",
        "confidence": "high",
    },
    {
        "from_node": "media-palantir-luckey",
        "to_node": "pntr-2000",
        "relationship": "VALIDATES",
        "detail": "Palmer Luckey publicly stated defense supply chain is broken",
        "confidence": "high",
    },
    {
        "from_node": "media-breaking-points",
        "to_node": "reshoring-2025",
        "relationship": "REPORTS_ON",
        "detail": "Covers populist economics, reshoring, tariff policy from independent perspective",
        "confidence": "medium",
    },
    {
        "from_node": "media-all-in-podcast",
        "to_node": "great-rotation-2026",
        "relationship": "REPORTS_ON",
        "detail": "Investor perspective on macro, tariffs, reshoring economics",
        "confidence": "medium",
    },
    {
        "from_node": "media-substack-ecosystem",
        "to_node": "china-shock",
        "relationship": "REPORTS_ON",
        "detail": "Multiple independent writers documenting industrial decline",
        "confidence": "medium",
    },
    {
        "from_node": "media-reddit-wsb",
        "to_node": "great-rotation-2026",
        "relationship": "REPORTS_ON",
        "detail": "Retail investor awareness of reshoring thesis, ETF discussions",
        "confidence": "low",
    },

    # Accountability edges: what enabled crimes
    {
        "from_node": "pntr-2000",
        "to_node": "crime-fentanyl-pipeline",
        "relationship": "ENABLED",
        "detail": "PNTR normalized trade with China → enabled chemical precursor supply chains → ~100K deaths/year",
        "confidence": "high",
    },
    {
        "from_node": "pntr-2000",
        "to_node": "crime-forced-labor-xinjiang",
        "relationship": "ENABLED",
        "detail": "PNTR enabled supply chains dependent on Xinjiang forced labor",
        "confidence": "high",
    },
    {
        "from_node": "hsbc",
        "to_node": "crime-hsbc-laundering",
        "relationship": "PROFITED_FROM",
        "detail": "HSBC (6.1% NY Fed owner) laundered cartel money. $1.92B fine, zero executives imprisoned.",
        "confidence": "high",
    },
    {
        "from_node": "blackrock",
        "to_node": "crime-forced-labor-xinjiang",
        "relationship": "PROFITED_FROM",
        "detail": "$1.9B invested in 63 blacklisted Chinese companies per House CCP Committee",
        "confidence": "high",
    },
    {
        "from_node": "us-chamber-of-commerce",
        "to_node": "crime-refugee-resettlement-fraud",
        "relationship": "ENABLED",
        "detail": "Chamber lobbied for expanded immigration programs → created scale enabling oversight gaps",
        "confidence": "medium",
    },
    {
        "from_node": "crime-haugen-coordination",
        "to_node": "crime-censorship-infrastructure",
        "relationship": "COORDINATED_WITH",
        "detail": "Haugen testimony timing aligned with Biden administration push for platform regulation",
        "confidence": "medium",
    },
]


def load_signal_layer(conn: sqlite3.Connection) -> Tuple[int, int]:
    """
    Load signal and accountability layer nodes and edges.

    Returns (nodes_created, edges_created).
    """
    cursor = conn.cursor()
    nodes_created = 0
    edges_created = 0

    # Load signal nodes
    for node in SIGNAL_NODES:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO nodes (node_id, name, node_type, metadata)
                VALUES (?, ?, ?, ?)
            """, (
                node['node_id'],
                node['name'],
                node['node_type'],
                json.dumps(node.get('metadata', {})),
            ))
            if cursor.rowcount > 0:
                nodes_created += 1
        except sqlite3.IntegrityError:
            pass

    # Load accountability nodes
    for node in ACCOUNTABILITY_NODES:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO nodes (node_id, name, node_type, metadata)
                VALUES (?, ?, ?, ?)
            """, (
                node['node_id'],
                node['name'],
                node['node_type'],
                json.dumps(node.get('metadata', {})),
            ))
            if cursor.rowcount > 0:
                nodes_created += 1

            # Add sources from metadata
            metadata = node.get('metadata', {})
            source_urls = metadata.get('source_urls', [])
            if metadata.get('source_url'):
                source_urls.append(metadata['source_url'])

            for url in source_urls:
                source_id = source_id_from_url(url)
                cursor.execute("""
                    INSERT OR IGNORE INTO sources (source_id, url, domain, tier, retrieved_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (source_id, url, get_domain(url), get_tier(url)))

        except sqlite3.IntegrityError:
            pass

    # Load edges
    for edge in SIGNAL_EDGES:
        # Verify nodes exist
        cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (edge['from_node'],))
        if not cursor.fetchone():
            continue

        cursor.execute("SELECT node_id FROM nodes WHERE node_id = ?", (edge['to_node'],))
        if not cursor.fetchone():
            continue

        # Find or create a claim for this edge
        claim_text = f"{edge['from_node']} {edge['relationship']} {edge['to_node']}"
        if edge.get('detail'):
            claim_text += f" ({edge['detail']})"

        # Get topic from relationship
        topic = 'Signal' if edge['relationship'] in ['REPORTS_ON', 'VALIDATES'] else 'Accountability'

        cursor.execute("SELECT MAX(CAST(SUBSTR(claim_id, 6) AS INTEGER)) FROM claims")
        max_num = cursor.fetchone()[0] or 0
        claim_id = f"FGIP-{max_num + 1:06d}"

        cursor.execute("""
            INSERT INTO claims (claim_id, claim_text, topic, status, required_tier)
            VALUES (?, ?, ?, 'PARTIAL', 2)
        """, (claim_id, claim_text, topic))

        try:
            cursor.execute("""
                INSERT INTO edges (from_node, to_node, relationship, detail, claim_id, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                edge['from_node'],
                edge['to_node'],
                edge['relationship'],
                edge.get('detail'),
                claim_id,
                edge.get('confidence', 'medium'),
            ))
            edges_created += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    return nodes_created, edges_created


def get_signal_sources(conn: sqlite3.Connection) -> List[Dict]:
    """Get all independent media/signal nodes."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT node_id, name, node_type, metadata
        FROM nodes
        WHERE json_extract(metadata, '$.signal_type') IS NOT NULL
        ORDER BY node_type, name
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_accountability_cases(conn: sqlite3.Connection) -> List[Dict]:
    """Get all crime/fraud nodes."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT node_id, name, metadata
        FROM nodes
        WHERE json_extract(metadata, '$.type') IN
            ('fraud', 'money_laundering', 'narcotics_trafficking',
             'human_rights_abuse', 'government_overreach', 'coordinated_narrative')
        ORDER BY name
    """)
    return [dict(row) for row in cursor.fetchall()]


def trace_crime_enablers(conn: sqlite3.Connection, crime_node: str) -> List[Dict]:
    """Trace what enabled a specific crime."""
    cursor = conn.cursor()

    # Find direct enablers
    cursor.execute("""
        SELECT e.*, fn.name as from_name, c.claim_text
        FROM edges e
        JOIN nodes fn ON e.from_node = fn.node_id
        LEFT JOIN claims c ON e.claim_id = c.claim_id
        WHERE e.to_node = ? AND e.relationship IN ('ENABLED', 'PROFITED_FROM', 'COORDINATED_WITH')
    """, (crime_node,))

    return [dict(row) for row in cursor.fetchall()]


def crime_downstream(conn: sqlite3.Connection, legislation_node: str) -> List[Dict]:
    """Find crimes enabled by specific legislation."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT e.*, tn.name as to_name, tn.metadata as crime_metadata, c.claim_text
        FROM edges e
        JOIN nodes tn ON e.to_node = tn.node_id
        LEFT JOIN claims c ON e.claim_id = c.claim_id
        WHERE e.from_node = ? AND e.relationship = 'ENABLED'
    """, (legislation_node,))

    return [dict(row) for row in cursor.fetchall()]


if __name__ == '__main__':
    from schema import init_db

    db_path = 'fgip.db'
    conn = init_db(db_path)

    print("Loading signal and accountability layer...")
    nodes, edges = load_signal_layer(conn)
    print(f"  Created {nodes} nodes")
    print(f"  Created {edges} edges")

    print("\nSignal sources:")
    for src in get_signal_sources(conn)[:5]:
        print(f"  - {src['name']} ({src['node_type']})")

    print("\nAccountability cases:")
    for case in get_accountability_cases(conn)[:5]:
        print(f"  - {case['name']}")

    conn.close()
