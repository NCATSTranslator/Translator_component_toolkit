"""Visualization helpers for the Translator Component Toolkit.

All plotting and graph-rendering functions live here so that
``TCT.py`` stays focused on data retrieval and transformation.
"""

from dataclasses import dataclass as _dataclass

import ipycytoscape
import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
import seaborn as sns
from IPython.display import display
from pyvis.network import Network

from .node_normalizer import ID_convert_to_preferred_name_nodeNormalizer
from .results import dataframe_to_graph


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _convert_ids_to_names(id_list):
    """Return preferred names for CURIEs as a list, falling back to original IDs."""
    name_map = ID_convert_to_preferred_name_nodeNormalizer(id_list)
    return [name_map.get(curie, curie) for curie in id_list]


def _default_graph_style(edge_attr_column):
    """Return a unified Cytoscape style list for graph visualizations."""
    return [
        {'selector': 'node[id]',
         'style': {
             'font-family': 'Arial',
             'font-size': '12px',
             'text-valign': 'center',
             'text-halign': 'center',
             'label': 'data(id)',
         }},
        {'selector': 'node',
         'style': {
             'background-color': 'lightblue',
             'shape': 'round-rectangle',
             'width': 'label',
             'height': 'label',
             'padding': '10px',
         }},
        {'selector': f'edge[{edge_attr_column}]',
         'style': {
             'label': f'data({edge_attr_column})',
             'font-size': '8px',
             'text-background-color': '#ffffff',
             'text-background-opacity': 0.85,
             'text-background-padding': '3px',
             'text-background-shape': 'roundrectangle',
             'text-rotation': 'autorotate',
             'z-compound-depth': 'top',
         }},
        {"selector": "edge.directed",
         "style": {
             "curve-style": "bezier",
             "target-arrow-shape": "triangle",
         }},
        {"selector": "edge",
         "style": {
             "curve-style": "bezier",
         }},
    ]


# ---------------------------------------------------------------------------
# Heatmap functions
# ---------------------------------------------------------------------------

@_dataclass
class HeatmapConfig:
    """Configuration for heatmap rendering."""
    dpi: int = 300
    figsize_multiplier: float = 0.11
    title: str | None = None
    ylabel: str | None = None
    show: bool = True
    save: bool = False
    auto_tick_fontsize: bool = True


def _plot_heatmap_impl(predicates_by_nodes_df, num_of_nodes, fontsize, title_fontsize, output_png, config):
    """Shared implementation for heatmap plotting."""
    df = predicates_by_nodes_df.iloc[:,0:num_of_nodes]
    if df.empty:
        print("No data to plot in the heatmap. Please check your input data.")
        return
    fig = plt.figure(figsize=(0.8+df.shape[1]*config.figsize_multiplier, 3.5), dpi=config.dpi)
    ax = fig.add_subplot(111)

    p1 = sns.heatmap(df, cmap="Blues", cbar=False, ax=ax, linecolor='grey', linewidth=0.2)
    if config.auto_tick_fontsize:
        p1.set_xticklabels(p1.get_xticklabels(), rotation=90, fontsize=fontsize)
        p1.set_yticklabels(p1.get_yticklabels(), fontsize=fontsize)
    if config.title:
        p1.set_title(config.title)
    if config.ylabel:
        p1.set_ylabel(config.ylabel)
    plt.xticks(ticks=range(len(df.columns)), labels=df.columns)
    p1.title.set_size(title_fontsize)

    if config.save:
        plt.savefig(output_png, bbox_inches='tight', dpi=300)
    if config.show:
        plt.show()


def plot_heatmap(predicates_by_nodes_df,num_of_nodes = 20,
                                 fontsize = 6,
                                 title_fontsize = 10,
                                 output_png="NE_heatmap.png"):
    _plot_heatmap_impl(predicates_by_nodes_df, num_of_nodes, fontsize, title_fontsize, output_png,
                       HeatmapConfig(dpi=300, figsize_multiplier=0.11, show=True, save=False, auto_tick_fontsize=True))


def plot_heatmap_ui(predicates_by_nodes_df,num_of_nodes = 20,
                                 fontsize = 6,
                                 title_fontsize = 10,
                                 output_png="NE_heatmap.png"):
    _plot_heatmap_impl(predicates_by_nodes_df, num_of_nodes, fontsize, title_fontsize, output_png,
                       HeatmapConfig(dpi=100, figsize_multiplier=0.1,
                                     title="Ranking of one-hop nodes by primary infores",
                                     ylabel="infores", show=False, save=True, auto_tick_fontsize=False))


# ---------------------------------------------------------------------------
# One-hop ranking visualizations
# ---------------------------------------------------------------------------

def visulization_one_hop_ranking_input_as_list(result_ranked_by_primary_infores,result_parsed ,
                                 num_of_nodes = 20,
                                 input_query = "NCBIGene:3845",
                                 fontsize = 6,
                                 title_fontsize = 12,
                                 output_png1="NE_heatmap1.png",
                                 output_png2="NE_heatmap2.png"
                                 ):
    # edited Dec 5, 2023
    predicates_list = []
    primary_infore_list = []
    aggregator_infore_list = []

    for i in range(0, result_ranked_by_primary_infores.shape[0]):
        oupput_node = result_ranked_by_primary_infores['output_node'][i]
        type_of_node = result_ranked_by_primary_infores['type_of_nodes'][i]
        if type_of_node == 'object':
            subject = input_query
            obj = oupput_node
        else:
            subject = oupput_node
            obj = input_query

        predicates_list = predicates_list + result_parsed[subject + "_" + obj]['predicate']
        primary_infore_list = primary_infore_list + result_parsed[subject + "_" + obj]['primary_knowledge_source']

        if 'aggregator_knowledge_source' in result_parsed[subject + "_" + obj]:
            aggregator_infore_list = aggregator_infore_list + result_parsed[subject + "_" + obj]['aggregator_knowledge_source']
            aggregator_infore_list = list(set(aggregator_infore_list))

        predicates_list = list(set(predicates_list))
        primary_infore_list = list(set(primary_infore_list))


    predicates_by_nodes = {}
    for predict in predicates_list:
        predicates_by_nodes[predict] = []

    primary_infore_by_nodes = {}
    for predict in primary_infore_list:
        primary_infore_by_nodes[predict] = []

    aggregator_infore_by_nodes = {}
    for predict in aggregator_infore_list:
        aggregator_infore_by_nodes[predict] = []

    names = []
    for i in range(0, result_ranked_by_primary_infores.shape[0]):
    #for i in range(0, 10):
        # input_nodes = result_ranked_by_primary_infores['input_node'].values[i]  # Unused variable

        oupput_node = result_ranked_by_primary_infores['output_node'].values[i]
        names.append(oupput_node)
        type_of_node = result_ranked_by_primary_infores['type_of_nodes'].values[i]
        if type_of_node == 'object':
            subject = input_query
            obj = oupput_node
        else:
            subject = oupput_node
            obj = input_query
        new_id = subject + "_" + obj

        cur_primary_infore = result_parsed[new_id]['primary_knowledge_source']
        for predict in primary_infore_list:
            if predict in cur_primary_infore:
                primary_infore_by_nodes[predict].append(1)
            else:
                primary_infore_by_nodes[predict].append(0)



        cur_predicates = result_parsed[new_id]['predicate']
        for predict in predicates_list:
            if predict in cur_predicates:
                predicates_by_nodes[predict].append(1)
            else:
                predicates_by_nodes[predict].append(0)

    #convert = False

    #for item in colnames:
    #    if 'NCBIGene' in item:
    #        convert = True
    #if convert:
        #Gene_id_map = Gene_id_converter(colnames, "http://127.0.0.1:8000/query_name_by_id") # option 1
        #Gene_id_map = Generate_Gene_id_map() # option 2

    new_colnames = _convert_ids_to_names(names)

    primary_infore_by_nodes_df = pd.DataFrame(primary_infore_by_nodes)
    primary_infore_by_nodes_df.index = new_colnames
    primary_infore_by_nodes_df = primary_infore_by_nodes_df.T


    predicates_by_nodes_df = pd.DataFrame(predicates_by_nodes)
    predicates_by_nodes_df.index = new_colnames
    predicates_by_nodes_df = predicates_by_nodes_df.T

    plot_heatmap(primary_infore_by_nodes_df, num_of_nodes, fontsize, title_fontsize,output_png1)
    plot_heatmap(predicates_by_nodes_df, num_of_nodes, fontsize, title_fontsize,output_png2)

    return(predicates_by_nodes_df)

# Used. Jan 5, 2024
def visulization_one_hop_ranking(result_ranked_by_primary_infores,result_parsed ,
                                 num_of_nodes = 20,
                                 input_query = "NCBIGene:3845",
                                 fontsize = 6,
                                 title_fontsize = 12,
                                 output_png1="NE_heatmap1.png",
                                 output_png2="NE_heatmap2.png"
                                 ):
    # edited Dec 5, 2023
    # if result_parsed is empty, print a message and return an empty dataframe
    if result_parsed == {}:
        print("No results found in result_parsed. Please check your input data.")
        return pd.DataFrame()

    predicates_list = []
    primary_infore_list = []
    aggregator_infore_list = []

    for i in range(0, result_ranked_by_primary_infores.shape[0]):
        oupput_node = result_ranked_by_primary_infores['output_node'][i]
        type_of_node = result_ranked_by_primary_infores['type_of_nodes'][i]
        if type_of_node == 'object':
            subject = input_query
            obj = oupput_node
        else:
            subject = oupput_node
            obj = input_query

        predicates_list = predicates_list + result_parsed[subject + "_" + obj]['predicate']
        primary_infore_list = primary_infore_list + result_parsed[subject + "_" + obj]['primary_knowledge_source']

        if 'aggregator_knowledge_source' in result_parsed[subject + "_" + obj]:
            aggregator_infore_list = aggregator_infore_list + result_parsed[subject + "_" + obj]['aggregator_knowledge_source']
            aggregator_infore_list = list(set(aggregator_infore_list))

        predicates_list = list(set(predicates_list))
        primary_infore_list = list(set(primary_infore_list))


    predicates_by_nodes = {}
    for predict in predicates_list:
        predicates_by_nodes[predict] = []

    primary_infore_by_nodes = {}
    for predict in primary_infore_list:
        primary_infore_by_nodes[predict] = []

    aggregator_infore_by_nodes = {}
    for predict in aggregator_infore_list:
        aggregator_infore_by_nodes[predict] = []

    names = []
    for i in range(0, result_ranked_by_primary_infores.shape[0]):
    #for i in range(0, 10):
        oupput_node = result_ranked_by_primary_infores['output_node'].values[i]
        names.append(oupput_node)
        type_of_node = result_ranked_by_primary_infores['type_of_nodes'].values[i]
        if type_of_node == 'object':
            subject = input_query
            obj = oupput_node
        else:
            subject = oupput_node
            obj = input_query
        new_id = subject + "_" + obj

        cur_primary_infore = result_parsed[new_id]['primary_knowledge_source']
        for predict in primary_infore_list:
            if predict in cur_primary_infore:
                primary_infore_by_nodes[predict].append(1)
            else:
                primary_infore_by_nodes[predict].append(0)



        cur_predicates = result_parsed[new_id]['predicate']
        for predict in predicates_list:
            if predict in cur_predicates:
                predicates_by_nodes[predict].append(1)
            else:
                predicates_by_nodes[predict].append(0)

    #convert = False

    #for item in colnames:
    #    if 'NCBIGene' in item:
    #        convert = True
    #if convert:
        #Gene_id_map = Gene_id_converter(colnames, "http://127.0.0.1:8000/query_name_by_id") # option 1
        #Gene_id_map = Generate_Gene_id_map() # option 2

    new_colnames = _convert_ids_to_names(names)

    primary_infore_by_nodes_df = pd.DataFrame(primary_infore_by_nodes)
    primary_infore_by_nodes_df.index = new_colnames
    primary_infore_by_nodes_df = primary_infore_by_nodes_df.T


    predicates_by_nodes_df = pd.DataFrame(predicates_by_nodes)
    predicates_by_nodes_df.index = new_colnames
    predicates_by_nodes_df = predicates_by_nodes_df.T

    if not primary_infore_by_nodes_df.empty:
        plot_heatmap(primary_infore_by_nodes_df, num_of_nodes, fontsize, title_fontsize, output_png1)
    else:
        print("No primary infores found in primary_infore_by_nodes_df.")

    if not predicates_by_nodes_df.empty:
        plot_heatmap(predicates_by_nodes_df, num_of_nodes, fontsize, title_fontsize, output_png2)
    else:
        print("No predicates found in predicates_by_nodes_df.")
        return pd.DataFrame()

    return(predicates_by_nodes_df)


# ---------------------------------------------------------------------------
# Bar chart
# ---------------------------------------------------------------------------

def plot_path_bar(x,
                  y,
                    fontsize = 8,
                    title_fontsize = 10,
                    output_png="NE_heatmap.png"):
    #matplotlib.use('Agg')

    # title = "Bridging nodes"  # Unused variable
    fig = plt.figure(figsize=(5,5), dpi = 300)
    ax = fig.add_subplot(111)
    ax = sns.barplot(x=x, y=y, color='grey')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=90, ha="center", fontsize=fontsize)
    ax.set_ylabel("Ranking score")
    ax.title.set_size(title_fontsize)
    # save the figure
    plt.savefig(output_png, bbox_inches='tight', dpi=300)


# ---------------------------------------------------------------------------
# Cytoscape graph visualizations
# ---------------------------------------------------------------------------

def _plot_graph_by_attribute(for_plot, edge_attr_column):
    """Shared implementation for graph visualization by a given edge attribute."""
    graph = dataframe_to_graph(for_plot, edge_attrs=[edge_attr_column])

    graph_style = _default_graph_style(edge_attr_column)

    undirected = ipycytoscape.CytoscapeWidget()
    undirected.graph.add_graph_from_networkx(graph)
    undirected.set_layout(name='cose', title='Path', nodeSpacing=80, edgeLengthVal=50)
    undirected.set_style(graph_style)
    display(undirected)


def plot_graph_by_predicates(for_plot):
    _plot_graph_by_attribute(for_plot, "Predicate")


def plot_graph_by_infores(for_plot):
    _plot_graph_by_attribute(for_plot, "Infores")


def plot_graph_by_API(for_plot):
    _plot_graph_by_attribute(for_plot, "API")


# ---------------------------------------------------------------------------
# Path visualization
# ---------------------------------------------------------------------------

def visulize_path(input_node1_id, intermediate_node, input_node3_id, result, result2):
    forplot_subject = []
    forplot_object = []
    forplot_predicate = []
    forplot_Infores = []

    for k in result.keys():
        if (result[k]['object'] == intermediate_node and result[k]['subject'] == input_node1_id) or (result[k]['subject'] == intermediate_node and result[k]['object'] == input_node1_id)  :
            forplot_subject.append(result[k]['subject'])
            forplot_object.append(result[k]['object'])
            #forplot_predicate.append(result[k]['predicate'].split(':')[1])
            cur_sources_list = []
            sources = result[k]['sources']

            for s in sources:
                cur_source = s['resource_id']
                cur_sources_list.append(cur_source)

            forplot_Infores.append(cur_sources_list)

            forplot_predicate.append(result[k]['predicate'].split(':')[1] + "::" + cur_sources_list[0])

    for k in result2.keys():
        if (result2[k]['object'] == intermediate_node and result2[k]['subject'] ==input_node3_id ) or (result2[k]['subject'] == intermediate_node and result2[k]['object'] ==input_node3_id)  :
            forplot_subject.append(result2[k]['subject'])
            forplot_object.append(result2[k]['object'])
            #forplot_predicate.append(result2[k]['predicate'].split(':')[1])
            cur_sources_list = []
            sources = result2[k]['sources']

            for s in sources:
                cur_source = s['resource_id']
                cur_sources_list.append(cur_source)

            forplot_Infores.append(cur_sources_list)
            forplot_predicate.append(result2[k]['predicate'].split(':')[1] + "::" +  cur_sources_list[0])

    forplot =  pd.DataFrame({"Subject":forplot_subject, "Object":forplot_object, "Predicates":forplot_predicate})

    # get preferred name
    subject_name = list(forplot["Subject"] )
    object_name = list(forplot["Object"])
    all_names = _convert_ids_to_names(subject_name + object_name)
    forplot['Subject_name'] = all_names[:len(subject_name)]
    forplot['Object_name'] = all_names[len(subject_name):]

    forplot = forplot.drop_duplicates()

    # add two columns for forplot named check1 = Subject_name + '::' + Predicates + '::' + Object_name, and check2 = Object_name + '::' + Predicates + '::' + Subject_name
    # if check1 is equal to check2, then drop one of them
    forplot['check1'] = forplot['Subject_name'] + '::' + forplot['Predicates'] + '::' + forplot['Object_name']
    forplot['check2'] = forplot['Object_name'] + '::' + forplot['Predicates'] + '::' + forplot['Subject_name']

    # check if check1 is equal to check2, if so, drop one of them
    to_be_dropped = []
    check1_list = list(forplot['check1'].values)
    check2_list = list(forplot['check2'].values)

    for i in range(0,len(check1_list)-1):
        for j in range(i, len(check1_list)):
            if check1_list[i] == check2_list[j] and check2_list[i] == check1_list[j]:
                to_be_dropped.append(i)
                break
                #break
    to_be_dropped
    forplot = forplot.drop(to_be_dropped, axis=0)
    # remove the check1 and check2 columns
    forplot = forplot.drop(['check1', 'check2'], axis=1)

    forplot = forplot.reset_index(drop=True)

    graph = nx.from_pandas_edgelist(forplot, source='Subject_name', target='Object_name', edge_attr=[ 'Predicates'], create_using=nx.MultiGraph)

    graph_style = _default_graph_style('Predicates')

    pathgraph = ipycytoscape.CytoscapeWidget()
    pathgraph.graph.add_graph_from_networkx(graph)
    pathgraph.set_layout(name='cose', title='Path', nodeSpacing=80, edgeLengthVal=50)
    pathgraph.set_style(graph_style)

    display(pathgraph)
    return(forplot)


# ---------------------------------------------------------------------------
# Neighborhood graph (pyvis)
# ---------------------------------------------------------------------------

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
        dic_graph = visualize_neiborhood_graph(result, show_label=True, height="500", width="100%")
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
    dic_graph = {}
    predicate_list = set()
    # Add subject, object, and predicate as an edge
    for key in data:
        item = data[key]
        if show_label:
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
