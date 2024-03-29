from typing import Union
import networkx as nx

import ibdiag
import ibdiag_xlsx
import argparse
import time
import sys
import random
import os
import re

import matplotlib
import matplotlib.pyplot as plt
matplotlib.use("agg")
# matplotlib.use("pdf")
# matplotlib.use("macosx")

# import bokeh.io
# import bokeh.plotting
# import bokeh.models
# import bokeh.palettes

def count_edges_for(edge_list, start, end):
    result = 0
    for s, e, k in edge_list:
        if start == s and end == e:
            result += 1
    return result

def short_speed_info(speedinfo):
    return ibdiag.short_speed_info(speedinfo)

def get_speed_edge_color(speedinfo):
    if short_speed_info(speedinfo) == "200Gb":
        return "purple"
    if short_speed_info(speedinfo) == "100Gb":
        return "black"
    if short_speed_info(speedinfo) == "56Gb":
        return "blue"
    if short_speed_info(speedinfo) == "40Gb":
        return "orange"
    if short_speed_info(speedinfo) == "10Gb":
        return "red"
    return "red"

# def do_bokeh_html_graph(gnx, pos, filename):
#     tooltips_nodes = [("name", "@names"), ("lid", "@index"), ("port", "@ports")]
#     plot = bokeh.plotting.figure(title="Infiniband Map",
#                                x_range=(-660, 660), y_range=(-1000, 1000),
#                                sizing_mode='scale_width', active_scroll='wheel_zoom',
#                                tools="pan,wheel_zoom,save,reset,tap,box_zoom")
#    plot.axis.visible = False
#    bg = bokeh.plotting.from_networkx(gnx, nx.multipartite_layout, scale=100, center=(0, 0),
#                                      subset_key="layer", align='horizontal')
#    bg_pos = bg.layout_provider.graph_layout
#    bg_source = bg.node_renderer.data_source
#    bg_data = bg_source.data
#    bg_data['x'] = [0]*len(pos)
#    bg_data['y'] = [0]*len(pos)
#    for k, v in bg_pos.items():
#        bg_data['x'][bg_data['index'].index(k)] = v[0] - 1
#        bg_data['y'][bg_data['index'].index(k)] = v[1] - 1
#    labels = bokeh.models.LabelSet(x='x', y='y', text='names', source=bg_source, render_mode='canvas')
#    plot.add_layout(labels)
#
#    bg.node_renderer.glyph = bokeh.models.Ellipse(name='names', fill_color='colors',
#                                                  height='heights', width='widths', line_width=1)
#    bg.edge_renderer.glyph = bokeh.models.MultiLine(line_color='color', line_alpha=0.8, line_width=1)
#    node_hover_tool = bokeh.models.HoverTool(renderers=[bg.node_renderer], tooltips=tooltips_nodes)
#    plot.add_tools(node_hover_tool)
# 
#    plot.renderers.append(bg)
#    point_drag = bokeh.models.PointDrawTool(renderers=[bg.node_renderer])
#    plot.add_tools(point_drag)
#    plot.toolbar.active_tap = None
#    plot.toolbar.active_drag = point_drag
#    bokeh.selection_policy = bokeh.models.NodesAndLinkedEdges()
#    bokeh.inspection_policy = bokeh.models.EdgesAndLinkedNodes()
#    bokeh.io.output_file(filename + ".html")
#    print("Plotting bokeh html")
#    bokeh.io.save(plot)

def expand_hostlist(args, endpoints):
    hosts = args.graph_subset

    hosts_l = hosts.split(",")
    if len(hosts_l) > 1:
        hosts_l = "^(" + "|".join(hosts_l) + ")$"
    else:
        hosts_l = hosts_l[0]
    regex = re.compile(hosts_l)
    hostnames, _ = ibdiag.get_hostinfo_tables(endpoints)
    result_list = []
    for h in hostnames:
        if regex.match(h):
            result_list.append(h)
    print(result_list)
    result_list = ",".join(result_list)
    return result_list

def graph_add_core_node_attrs(node_attrs, lid, type, color, width, height=None, label=None):
    node_attrs['types'][lid] = type
    node_attrs['colors'][lid] = color
    node_attrs['widths'][lid] = width
    if height is not None:
        node_attrs['heights'][lid] = height
    if label is not None:
        node_attrs['labels'][lid] = label
    
def graph_add_edge_attrs(edge_attrs, edge, type, color, width, label=None):
    edge_attrs['colors'][edge] = color
    edge_attrs['types'][edge] = type
    edge_attrs['widths'][edge] = width
    if label is not None:
        edge_attrs['labels'][edge] = label

def graph_add_switch(sw, lid, gnx, core_layer, sw_layer, isl_edges, node_attrs, edge_attrs, sw_label = None):
    core_sw = 0
    if len(sw.endpoints) == 0:
        # outer_list[0].append(lid)
        core_sw = 1
        gnx.add_node(lid, layer=core_layer, size=20)
        graph_add_core_node_attrs(node_attrs, lid, 'core switch', 'lightgreen', 25, 10, label=sw_label)
    else:
        # outer_list[2].append(lid)
        gnx.add_node(lid, layer=sw_layer, size=20)
        graph_add_core_node_attrs(node_attrs, lid, 'leaf switch', 'skyblue', 25, 10, label=sw_label)
    for p, (dest_sw, dest_swp, speed) in sw.isls.items():
        # print("Destport, Speed: ", dest_swp, speed)
        edge = (lid, dest_sw.lid, gnx.new_edge_key(lid, dest_sw.lid))
        isl_edges.append(edge)
        isl_label = f"{short_speed_info(speed)}"
        if (edge[2] > 0):
            isl_label += f" (x{edge[2] + 1})"
        gnx.add_edge(lid, dest_sw.lid, label=isl_label)
        graph_add_edge_attrs(edge_attrs, edge, 'isl', get_speed_edge_color(speed), 1)
    return core_sw

def graph_draw_nx_edges(gnx, pos, widths):
    drawn = []
    arrowstyle = "<|-|>"
    for e in gnx.edges(keys=True, data=True):
        (u, v, key, data) = e
        # print(e)
        if (v, u, key) in drawn:
            continue
        rad = .01 * (key + 1)
        if key % 2 == 0:
            rad = -rad
        arcstyle = "arc3,rad=" + str(rad)
        nx.draw_networkx_edges(gnx, pos, edgelist=[e], connectionstyle=arcstyle, width=data['width'], 
            edge_color=data['color'], node_size=widths, arrowstyle=arrowstyle)
        drawn.append((u, v, key))
    edge_labels_dict = {}
    for (u, v, data) in gnx.edges.data(keys=False):
        edge_labels_dict[(u, v)] = data['label']
    nx.draw_networkx_edge_labels(gnx, pos, edge_labels=edge_labels_dict)

def set_nx_node_attributes(gnx, node_attrs):
    nx.set_node_attributes(gnx, node_attrs['types'], 'types')
    nx.set_node_attributes(gnx, node_attrs['colors'], 'colors')
    nx.set_node_attributes(gnx, node_attrs['labels'], 'names')
    nx.set_node_attributes(gnx, node_attrs['heights'], 'heights')
    nx.set_node_attributes(gnx, node_attrs['widths'], 'widths')
    nx.set_node_attributes(gnx, node_attrs['ports'], 'ports')

def set_nx_edge_attributes(gnx, edge_attrs):
    nx.set_edge_attributes(gnx, edge_attrs['labels'], 'label')
    nx.set_edge_attributes(gnx, edge_attrs['colors'], 'color')
    nx.set_edge_attributes(gnx, edge_attrs['widths'], 'width')
    nx.set_edge_attributes(gnx, edge_attrs['types'], 'type')


def update_switch_layer_info(sw_layer, core_layer, uppertotal, lowertotal, added_count):
    if sw_layer > core_layer:
        uppertotal += added_count
    else:
        lowertotal += added_count
    if (uppertotal >= lowertotal and sw_layer > core_layer) or (uppertotal <= lowertotal and sw_layer < core_layer):
        sw_layer = -sw_layer
    return sw_layer, core_layer, uppertotal, lowertotal

def adjust_positions(pos, switches, figsize):
    print(f"len pos: {len(pos)}, switches: {len(switches)}, figsize={figsize}")
    ep_adjustx = .2/13   # shift within layer/number layers
    sw_adjustx, sw_adjusty = 0, 0
    if len(switches) > 2:
        sw_adjustx = ep_adjustx * 3.0
        num_ep_rows = (len(pos) - len(switches))/6.0
        sw_adjusty = max(1, num_ep_rows/len(switches))
    for i, (k, v) in enumerate(pos.items()):
        # print(k, v)
        shift = (i % 2) - 0.5
        if k in switches:
            v[1] = v[1] * sw_adjusty
            if len(switches[k].endpoints.items()) > 0:
                v[0] = v[0] - (sw_adjustx * shift)
            # print(f"Switch: {k} coord: {v}")
        else:
            v[0] = v[0] - (ep_adjustx * shift)

def do_switch_graph(switches, filename="graph", host_list=None):
    labeldict = {}
    isl_edges, isl_nodes, end_edges, end_nodes = [], [], [], []
    if host_list is not None:
        host_list = host_list.replace(" ", "")
        host_list = host_list.split(",")

    core_layer, sw_layer = 0, 2
    core_count = 0
    uppertotal = lowertotal = 0
    node_attrs = {'types': {}, 'colors': {}, 'labels': {}, 'names': {}, 'heights': {}, 'widths': {}, 'ports': {}}
    edge_attrs = {'labels': {}, 'types': {}, 'colors': {}, 'widths': {}}
    gnx = nx.MultiDiGraph()
    for lid, sw in switches.items():
        isl_nodes.append(lid)
        sw_display_name = sw.name.replace(" - ", "- ")
        sw_display_name = sw_display_name.replace(" ", "\n")
        sw_label = f"{sw_display_name}\n{len(sw.connections)}/{sw.portcount} ports up\n(lid {lid})"
        core_count += graph_add_switch(sw, lid, gnx, core_layer, sw_layer, isl_edges, node_attrs, edge_attrs, sw_label=sw_label)
        endpoints_added = 0
        for port, ep in sw.endpoints.items():
            if host_list is None or ibdiag.get_portstripped_hostname(ep.name) in host_list:
                labeldict[ep.lid] = ep.name
                end_nodes.append(ep.lid)
                endpoints_added += 1
                if sw_layer < core_layer:
                    #ep_layer = sw_layer - random.randrange(3, 6)
                    ep_layer = sw_layer - ((ep.lid % 3) + 3)
                else:
                    #ep_layer = sw_layer + random.randrange(3, 6)
                    ep_layer = sw_layer + ((ep.lid % 3) + 3)
                gnx.add_node(ep.lid, layer=ep_layer)
                if ep.name.find("weka") > -1:
                    node_color = "lavender"
                else:
                    node_color = "wheat"
                node_label = ep.name.replace(' ', '\n') + f"\nport {port}\n{ep.lid}"
                node_attrs['ports'][ep.lid] = port
                graph_add_core_node_attrs(node_attrs, ep.lid, 'node', node_color, 12, 4, label = node_label)
                node_edge = (ep.switch.lid, ep.lid, gnx.new_edge_key(ep.switch.lid, ep.lid))
                end_edges.append(node_edge)
                edge_label = f"port {port} ({short_speed_info(ep.speed)})"
                graph_add_edge_attrs(edge_attrs, node_edge, 'edge', get_speed_edge_color(ep.speed), 1, label=edge_label)
        sw_layer, core_layer, uppertotal, lowertotal = \
            update_switch_layer_info(sw_layer, core_layer, uppertotal, lowertotal, endpoints_added)
 
    set_nx_node_attributes(gnx, node_attrs)
    gnx.add_edges_from(end_edges)
    set_nx_edge_attributes(gnx, edge_attrs)

    print(f"isl_edges len: {len(isl_edges)}, end_edges len: {len(end_edges)}")
    #for (s, e, k) in isl_edges:
    #    if k == 0:
    #        print(f"Between switches: {s} and {e} there are {count_edges_for(isl_edges, s, e)} ISL(s)")

    pos = nx.multipartite_layout(gnx, subset_key="layer", align='vertical', scale=1)
    figsize = max(50, uppertotal / 2.5, lowertotal / 2.5, len(switches))
    plt.figure(figsize=(figsize, figsize*1.3))
    adjust_positions(pos, switches, figsize)

    colors = [c for (i, c) in gnx.nodes(data='colors')]
    widths = [w*400 for (i, w) in gnx.nodes(data='widths')]
    time_a = time.time()
    nx.draw_networkx_nodes(gnx, pos, list(gnx.nodes()), node_size=widths, node_color=colors)
    nx.draw_networkx_labels(gnx, pos, labels=node_attrs['labels'])
    graph_draw_nx_edges(gnx, pos, widths)
    print(f"Calculating/adding edges and nodes took {time.time() - time_a} seconds.")
    # not useful for now - sizing, spread, and multiple edges not handled well yet
    # do_bokeh_html_graph(gnx, pos, filename)

    custom_legend_lines = [
        matplotlib.lines.Line2D([0], [0], color="purple", lw=4),
        matplotlib.lines.Line2D([0], [0], color="black", lw=4), matplotlib.lines.Line2D([0], [0], color="blue", lw=4),
        matplotlib.lines.Line2D([0], [0], color="orange", lw=4), matplotlib.lines.Line2D([0], [0], color="red", lw=4)
        ]
    plt.legend(custom_legend_lines, ['200Gb', '100Gb', '56Gb', '40Gb', '10Gb or other'], loc='lower left', fontsize=20)
    plt.title('Infiniband network', fontsize=30)
    time_a = time.time()
    plt.savefig(filename + ".pdf", bbox_inches='tight', pad_inches=0.5)
    print(f"plt.savefig took {time.time() - time_a} seconds.")
    plt.show()

def get_arg_parser(description="ibdiag_graph: Generate IB network map(s) and excel data file"):
    my_parser = ibdiag_xlsx.get_arg_parser(description=description)
    my_parser.add_argument("--graph_subset", dest="graph_subset", default=None,
                           help="comma separated list, or a regex, of names to be included in the graph")
    my_parser.add_argument("--graph_subset_file", dest="graph_subset_file", default="graph", 
        help="filename for graph subset output when --graph_subset is supplied")
    my_parser.add_argument("--graph_all_file", dest="graph_all_file", default="graph-full", 
        help="filename for full graph output; this file is always produced")
    my_parser.add_argument("--xlsx_only", dest="xlsx_only", action='store_true',
        help="if provided no graph(s) are generated, just a spreadsheet file")
    return my_parser

def get_args():
    my_parser = get_arg_parser()
    a = my_parser.parse_args()
    return a

def main():
    args = get_args()
    time_a = time.time()
    all_switches, all_endpoints = ibdiag.do_diag_run(args)
    print(f"Diag run took {time.time() - time_a} seconds.  Processed {len(all_switches)} switches.")
    print(all_switches)
    ibdiag_xlsx.write_xlsx(all_switches, all_endpoints, args.xlsx_file)
    if not args.xlsx_only:
        print(f"Creating full graph...")
        time_b = time.time()
        do_switch_graph(all_switches, filename=args.graph_all_file, host_list=None)
        print(f"Full graph took {time.time() - time_b}")
        if args.graph_subset is not None:
            time_b = time.time()
            print(all_endpoints)
            host_subset = expand_hostlist(args, all_endpoints)
            print(f"Creating graph with graph_subset list: {args.graph_subset}")
            print(f"hostlist expanded: {host_subset}")
            do_switch_graph(all_switches, filename=args.graph_subset_file, host_list=host_subset)
            print(f"SubGraph creation time: {time.time() - time_b} seconds.")
    print(f"Full run took {time.time() - time_a} seconds.")
    # print(f"Graph created and saved in {args.graph_file}.")

def use_uconn_sample_data():
    if len(sys.argv) == 1:
        datadir = ibdiag_xlsx.use_ucon_sample_data()
        clients = f"cn332,cn337,cn338,cn341,cn348,cn364,cn365,cn368,cn370,cn378,cn379,cn380," + \
                  f"cn382,cn383,cn384,cn385,cn386,cn387,cn391,cn394,cn395,cn403,cn406,cn407,"
        weka_backends = ",".join([f"weka{i:02}" for i in range(1, 13)])    # weka01..weka12
        ibdiag.add_argv_arg("--graph_all_file", datadir + "ucon-full") 
        ibdiag.add_argv_arg("--graph_subset_file", datadir + "ucon-subset")
        ibdiag.add_argv_arg("--graph_subset", clients + weka_backends)
        ibdiag.add_argv_arg("--skip_routing")
    
def use_peng_sample_data():
    if len(sys.argv) == 1:
        datadir = ibdiag_xlsx.use_peng_sample_data()
        ibdiag.add_argv_arg("--graph_all_file", datadir + "peng-full")

if __name__ == '__main__':
    # use_uconn_sample_data()
    # use_peng_sample_data()
    main()
