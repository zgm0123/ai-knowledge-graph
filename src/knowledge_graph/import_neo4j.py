#!/usr/bin/env python3
"""Script to import Neo4j knowledge graph data and visualize it using the project's visualization utilities."""
import argparse
import json
import os
import sys
# Add the project root directory to Python's path
# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))
# Go up three levels to reach the project root
grandparent_dir = os.path.abspath(os.path.join(current_dir, '../../..'))
sys.path.append(grandparent_dir)
print(f"Added project root to path: {grandparent_dir}")
from neo4j import GraphDatabase
from src.knowledge_graph.visualization import visualize_knowledge_graph
from src.knowledge_graph.config import load_config


def connect_to_neo4j(uri, username, password):
    """Establish a connection to Neo4j database."""
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
        print("Successfully connected to Neo4j database")
        return driver
    except Exception as e:
        print(f"Error connecting to Neo4j: {e}")
        return None


def fetch_triples_from_neo4j(driver, query=None):
    """
    Fetch triples (subject-predicate-object) from Neo4j database.

    Args:
        driver: Neo4j driver instance
        query: Custom Cypher query to fetch triples. If provided, must return
               'subject', 'predicate', and 'object' fields.

    Returns:
        List of dictionaries with 'subject', 'predicate', and 'object' keys
    """
    if not driver:
        print("Error: No Neo4j driver instance provided.")
        return []

    # Default query to fetch all relationships
    if not query:
        query = """
        MATCH (s)-[r]->(o)
        RETURN s.name AS subject, type(r) AS predicate, o.name AS object
        LIMIT 1000
        """
        print("Using default query to fetch triples.")
    else:
        print(f"Warning: Using custom query: {query}")
        print("Ensure the query returns 'subject', 'predicate', and 'object' fields.")

    triples = []
    try:
        with driver.session() as session:
            result = session.run(query)
            print("Query executed. Processing results...")
            record_count = 0
            for record in result:
                record_count += 1
                # Debug: Print the entire record to understand its structure
                print(f"Processing record: {record}")

                # Extract values from Neo4j record with error handling
                try:
                    # Handle potential case sensitivity issues
                    subject = str(record.get("subject", record.get("Subject", "")))
                    predicate = str(record.get("predicate", record.get("Predicate", "")))
                    object = str(record.get("object", record.get("Object", "")))
                except Exception as extraction_error:
                    print(f"Error extracting fields from record: {extraction_error}")
                    subject = predicate = object = ""

                # Validate we have all required fields
                if not all([subject, predicate, object]):
                    print(f"Warning: Skipping invalid triple: {record}")
                    print(f"  Details: subject='{subject}', predicate='{predicate}', object='{object}'")
                    continue

                # Additional check for empty strings after conversion
                if subject.strip() == '' or predicate.strip() == '' or object.strip() == '':
                    print(f"Warning: Skipping triple with empty values after conversion: {record}")
                    print(f"  Details: subject='{subject}', predicate='{predicate}', object='{object}'")
                    continue

                triple = {
                    "subject": subject,
                    "predicate": predicate,
                    "object": object
                }
                triples.append(triple)
        print(f"Total records processed: {record_count}")
        print(f"Successfully fetched {len(triples)} valid triples from Neo4j")
    except Exception as e:
        print(f"Error fetching triples from Neo4j: {e}")
        import traceback
        traceback.print_exc()

    return triples


def convert_neo4j_to_project_format(neo4j_data):
    """
    Convert Neo4j data to the format expected by the project's visualization function.

    Args:
        neo4j_data: Data fetched from Neo4j

    Returns:
        List of dictionaries in the project's format
    """
    # In this case, the format is already compatible if we fetched with the default query
    # But we'll add this function for potential future needs
    return neo4j_data


def main():
    """Main entry point for importing Neo4j data and visualizing it."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Import Neo4j data and visualize as knowledge graph')
    parser.add_argument('--uri', type=str, default='bolt://localhost:7687', help='Neo4j database URI')
    parser.add_argument('--username', type=str, default='neo4j', help='Neo4j username')
    parser.add_argument('--password', type=str, required=True, help='Neo4j password')
    parser.add_argument('--query', type=str, help='Custom Cypher query to fetch triples')
    parser.add_argument('--output', type=str, default='d:\\git\\ai-knowledge-graph\\docs\\neo4j_knowledge_graph.html', help='Output HTML file path')
    parser.add_argument('--config', type=str, default='config.toml', help='Path to configuration file')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)
    if not config:
        print(f"Failed to load configuration from {args.config}. Using defaults.")
        config = {}

    # Connect to Neo4j
    driver = connect_to_neo4j(args.uri, args.username, args.password)
    if not driver:
        print("Exiting due to Neo4j connection failure")
        return

    # Fetch triples from Neo4j
    neo4j_triples = fetch_triples_from_neo4j(driver, args.query)
    if not neo4j_triples:
        print("No triples fetched from Neo4j. Exiting.")
        return

    # Convert to project format (if needed)
    project_triples = convert_neo4j_to_project_format(neo4j_triples)

    # Save the data as JSON for potential reuse
    json_output = args.output.replace('.html', '.json')
    try:
        with open(json_output, 'w', encoding='utf-8') as f:
            json.dump(project_triples, f, indent=2)
        print(f"Saved Neo4j data to {json_output}")
    except Exception as e:
        print(f"Warning: Could not save data to {json_output}: {e}")

    # Visualize the knowledge graph
    stats = visualize_knowledge_graph(project_triples, args.output, config=config)

    print("\nKnowledge Graph Statistics:")
    print(f"Nodes: {stats['nodes']}")
    print(f"Edges: {stats['edges']}")
    print(f"Communities: {stats['communities']}")

    # Provide command to open the visualization in a browser
    print("\nTo view the visualization, open the following file in your browser:")
    print(f"file://{os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()