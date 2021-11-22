# ibdiag_graph

optional arguments:
-h, --help            show this help message and exit

--switch_info_file SWITCH_INFO_FILE file containing the results of the 'ibswitches' command

--link_info_file LINK_INFO_FILE file containing the results of the 'iblinkinfo --switches-only -l' command

--route_info_file ROUTE_INFO_FILE file containing the concatenated results of the 'ibroute `<switch lid>`' command, for all switches

--xlsx_file XLSX_FILE 	file name for .xlsx output file 

--graph_subset GRAPH_SUBSET 				comma separated list of names to be included in the graph

--graph_subset_file GRAPH_SUBSET_FILE 		filename for graph subset output when --graph_subset is supplie

--graph_all_file GRAPH_ALL_FILE 				filename for full graph output; this file is always produced

--skip_routing        		Skip gathering/calculating routing information

--xlsx_only	if provided no graph(s) are generated, just a spreadsheet file
