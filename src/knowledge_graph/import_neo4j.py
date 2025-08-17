#!/usr/bin/env python3
"""Script to import Neo4j knowledge graph data and visualize it using the project's visualization utilities.

This script supports three main graph query tasks:
1. Retrieve n-hop subgraph starting from a specific node
2. Retrieve all triples with a specific relationship type
3. Retrieve knowledge chain starting from a node with specific relationship

Usage examples:
# Task 1: Retrieve 2-hop subgraph starting from node "AI"
python import_neo4j.py --password your_password --n-hop 2 --node-id "AI" --node-label Entity

# Task 2: Retrieve all triples with "RELATED_TO" relationship
python import_neo4j.py --password your_password --relationship RELATED_TO

# Task 3: Retrieve knowledge chain from "AI" with "HAS_PART" relationship
python import_neo4j.py --password your_password --chain-node "AI" --chain-relationship HAS_PART --chain-label Entity
"""
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


def generate_n_hop_subgraph_query(node_id, n_hops, node_label="", direction="both"):
    """
    Generate Cypher query to retrieve n-hop subgraph starting from a given node.

    Args:
        node_id: ID or name of the starting node
        n_hops: Number of hops to include in the subgraph
        node_label: Optional label of the starting node (leave empty to match any label)
        direction: Relationship direction ('both', 'out', 'in') - default is 'both'

    Returns:
        Cypher query string
    """
    # 1. 构造标签片段
    label_clause = f":{node_label}" if node_label else ""

    # 2. 确定关系方向语法
    rel_dir = "-" if direction == "both" else "->" if direction == "out" else "<-"

    # 3. 构建Cypher查询：锁定起点 → 拉路径 → 拆开三元组
    query = f"""
    MATCH (start{label_clause}) WHERE start.name = $node_id
    MATCH path = (start){rel_dir}[*..{n_hops}]-(end)
    WITH nodes(path) AS nodes, relationships(path) AS rels
    UNWIND range(0, size(rels)-1) AS i
    RETURN nodes[i].name   AS subject,
           type(rels[i])   AS predicate,
           nodes[i+1].name AS object
    """

    query += " LIMIT 1000"
    return query


def generate_relationship_query(relationship_type):
    """
    Generate Cypher query to retrieve all triples with a specific relationship type.

    Args:
        relationship_type: Type of relationship to retrieve

    Returns:
        Cypher query string
    """
    return f"MATCH (s)-[r:{relationship_type}]->(o) RETURN s.name AS subject, type(r) AS predicate, o.name AS object LIMIT 1000"


def generate_knowledge_chain_query(start_node, relationship_type, start_label=""):
    """
    Generate Cypher query to retrieve knowledge chain starting from a node with specific relationship.

    Args:
        start_node: Name of the starting node
        relationship_type: Type of relationship to follow
        start_label: Optional label of the starting node (leave empty to match any label)

    Returns:
        Cypher query string
    """
    # 构造标签片段
    label_clause = f":{start_label}" if start_label else ""

    # 构建参数化Cypher查询
    query = f"MATCH path = (s{label_clause} {{name: $start_node}})-[:{relationship_type}*1..5]->(o) RETURN nodes(path) AS nodes, relationships(path) AS rels LIMIT 100"

    return query


def fetch_triples_from_neo4j(driver, query=None, params=None, is_chain_query=False):
    """
    Fetch triples (subject-predicate-object) from Neo4j database.

    Args:
        driver: Neo4j driver instance
        query: Custom Cypher query to fetch triples
        is_chain_query: Flag indicating if this is a knowledge chain query
                        that returns paths instead of direct triples

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
        if not is_chain_query:
            print("Ensure the query returns 'subject', 'predicate', and 'object' fields.")
        else:
            print("Query returns paths which will be converted to triples.")

    triples = []
    try:
        with driver.session() as session:
            if params:
                result = session.run(query, **params)
            else:
                result = session.run(query)
            print("Query executed. Processing results...")
            record_count = 0
            for record in result:
                record_count += 1
                # Debug: Print the entire record to understand its structure
                print(f"Processing record: {record}")

                if is_chain_query:
                    # Handle knowledge chain query results
                    try:
                        nodes = record.get("nodes", [])
                        rels = record.get("rels", [])
                        if len(nodes) < 2 or len(rels) < 1:
                            print(f"Warning: Skipping invalid path record: {record}")
                            continue

                        # Convert path to triples
                        for i in range(len(rels)):
                            try:
                                subject = str(nodes[i].get("name", ""))
                                predicate = str(rels[i].type)
                                object = str(nodes[i+1].get("name", ""))

                                # Validate fields
                                if not all([subject, predicate, object]) or \
                                   subject.strip() == '' or predicate.strip() == '' or object.strip() == '':
                                    print(f"Warning: Skipping invalid triple in path: subject='{subject}', predicate='{predicate}', object='{object}'")
                                    continue

                                triple = {
                                    "subject": subject,
                                    "predicate": predicate,
                                    "object": object
                                }
                                triples.append(triple)
                            except Exception as e:
                                print(f"Error processing path element: {e}")
                                continue
                    except Exception as e:
                        print(f"Error extracting path from record: {e}")
                        continue
                else:
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
    parser.add_argument('--password', type=str, default='Zgm123456', help='Neo4j password')
    parser.add_argument('--query', type=str, help='Custom Cypher query to fetch triples')
    parser.add_argument('--output', type=str, default='d:\\git\\ai-knowledge-graph\\docs\\neo4j_knowledge_graph.html', help='Output HTML file path')
    parser.add_argument('--config', type=str, default='config.toml', help='Path to configuration file')
    
    # Task 1: n-hop subgraph
    parser.add_argument('--n-hop', type=int, help='Number of hops for subgraph retrieval')
    parser.add_argument('--node-id', type=str, help='Node ID for subgraph retrieval')
    parser.add_argument('--node-label', type=str, default='', help='Optional node label for subgraph retrieval (leave empty to match any label)')
    parser.add_argument('--direction', type=str, default='both', choices=['both', 'out', 'in'], help='Relationship direction for subgraph retrieval (both, out, in)')
    
    # Task 2: Specific relationship
    parser.add_argument('--relationship', type=str, help='Specific relationship type to retrieve')
    
    # Task 3: Knowledge chain
    parser.add_argument('--chain-node', type=str, help='Starting node for knowledge chain')
    parser.add_argument('--chain-label', type=str, default='', help='Label of the starting node for knowledge chain (leave empty to match any label)')
    parser.add_argument('--chain-relationship', type=str, help='Relationship type for knowledge chain')

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

    # Determine which query to use based on provided arguments
    query = args.query
    is_chain_query = False
    
    # Task 1: n-hop subgraph
    if args.n_hop and args.node_id:
        print(f"Retrieving {args.n_hop}-hop subgraph starting from node: {args.node_id}")
        query = generate_n_hop_subgraph_query(args.node_id, args.n_hop, args.node_label, args.direction)
    
    # Task 2: Specific relationship
    elif args.relationship:
        print(f"Retrieving all triples with relationship: {args.relationship}")
        query = generate_relationship_query(args.relationship)
    
    # Task 3: Knowledge chain
    elif args.chain_node and args.chain_relationship:
        print(f"Retrieving knowledge chain from {args.chain_node} with relationship: {args.chain_relationship}")
        query = generate_knowledge_chain_query(args.chain_node, args.chain_relationship, args.chain_label)
        is_chain_query = True
    
    # Prepare query parameters
    query_params = None
    if args.n_hop and args.node_id:
        query_params = {'node_id': args.node_id, 'n_hops': args.n_hop}
    elif args.chain_node and args.chain_relationship:
        query_params = {'start_node': args.chain_node}

    # Fetch triples from Neo4j
    neo4j_triples = fetch_triples_from_neo4j(driver, query, query_params, is_chain_query)
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