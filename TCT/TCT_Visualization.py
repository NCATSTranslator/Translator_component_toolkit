
from .node_normalizer import ID_convert_to_preferred_name_nodeNormalizer

import networkx as nx
from pyvis.network import Network

def visualize_neighborhood_graph(result, show_label=True, height="1000px", width="100%", output_filename_prefix=None):
    '''Visualize the neighborhood graph using pyvis
    Args:
        result: the output from the KP query, a dictionary or json format
        show_label: whether to convert the node id to preferred name
        height: the height of the figure
        width: the width of the figure
        output_filename_prefix: if present, this is appended to the end of every output graph file.
    Returns:
        dic_graph: a dictionary of networkx graph for each predicate
    Example:
        dic_graph = visualize_neighborhood_graph(result, show_label=True, height="500", width="100%")
    '''
    
    # Your JSON (as Python dict)
    data = result
    IDs = []
    for key in result:
        IDs.append(result[key]['subject'])
        IDs.append(result[key]['object'])
    IDs = list(set(IDs))

    ID_map = ID_convert_to_preferred_name_nodeNormalizer(IDs)

    # Step 1: Create a graph
    G = nx.DiGraph()
    dic_graph = {}
    predicate_list = set()
    # Add subject, object, and predicate as an edge
    for key in data:
        item = data[key]
        if show_label == True:
            subject = ID_map[item["subject"]] if item["subject"] in ID_map else item["subject"]
            obj = ID_map[item["object"]] if item["object"] in ID_map else item["object"]
        else:
            subject = item["subject"]
            obj = item["object"]
            
       
        predicate = item["predicate"].strip("biolink:")
        if predicate not in predicate_list:
            dic_graph[predicate] = nx.DiGraph()
            predicate_list.add(predicate)
        dic_graph[predicate].add_node(subject, label=subject, group="subject")
        dic_graph[predicate].add_node(obj, label=obj, group="object")
        dic_graph[predicate].add_edge(subject, obj, label='')
            
        
        for attr in item["attributes"]:
            att_type = attr.get("attribute_type_id")
            original_attribute_name = attr.get("original_attribute_name")

            att_val  = attr.get("value")
            if att_type and att_val:
                if att_type in ['biolink:supporting_text',
                                'biolink:primary_knowledge_source' , 
                                'biolink:publications',
                                'primary_knowledge_source',
                                'publications']:
                    dic_graph[predicate][subject][obj][att_type] = att_val
                        # Attach as metadata on the edge

            if original_attribute_name == 'publications':
                dic_graph[predicate][subject][obj][original_attribute_name] = att_val

        for source in item["sources"]:
            resource_role = source.get("resource_role")
            resource_id = source.get("resource_id")

            if resource_id and resource_role:
                dic_graph[predicate][subject][obj][resource_role] = resource_id

    # Step 2: Visualize the graph using PyVis   
    for predicate in dic_graph:
        net = Network(height=height, width=width, notebook=True, cdn_resources="in_line")
        net.from_nx(dic_graph[predicate])

        # Remove edge labels before passing to PyVis
        for u, v, d in dic_graph[predicate].edges(data=True):
            d.pop("label", None)  # remove 'label' if it exists


        for e in net.edges:
            e["title"] = "\n".join([f"{k}: {v}" for k,v in dic_graph[predicate][e["from"]][e["to"]].items()])

        # add title in the figure
        title_html = f"<h3>Predicate: {predicate}</h3>"
        net.title = title_html + f"<p>Nodes: {net.num_nodes()} Edges: {net.num_edges()}</p>"
        if output_filename_prefix is None:
            net.show(f"{predicate}.html")
        else:
            net.show(f"{output_filename_prefix}{predicate}.html")
    return dic_graph
