import subprocess
# import multiprocessing
import time
import re
import argparse
import sys
import os

def get_args(allow_unknown_args=False):
    if allow_unknown_args:
        argparser = argparse.ArgumentParser(add_help=False)
    else:
        argparser = argparse.ArgumentParser(description="ibdiag")
    argparser.add_argument('starthost', nargs='?', default=None, help="first host for extra path checks")
    argparser.add_argument('otherhosts', nargs='*', default=None)
    argparser.add_argument("--switch_info_file", dest="switch_info_file", default = None, 
        help="file containing the results of the 'ibswitches' command")
    argparser.add_argument("--link_info_file", dest="link_info_file", default = None, 
        help="file containing the results of the 'iblinkinfo --switches-only -l' command")
    argparser.add_argument("--route_info_file", dest="route_info_file", default = None, 
        help="file containing the concatenated results of the 'ibroute <switch lid>' command, for all switches'")

    if allow_unknown_args:
        a, _ = argparser.parse_known_args()
    else:
        a = argparser.parse_args()
    return a

def run_cmd(cmd_args_list):
    output = ''
    try:
        proc = subprocess.Popen(cmd_args_list, stdout=subprocess.PIPE, universal_newlines=True)
        output = proc.communicate()[0]
    except subprocess.SubprocessError as exc:
        print(f"Error running {cmd_args_list}: {exc}")
    except FileNotFoundError as exc:
        print(exc)
        print(f"Error running {cmd_args_list}; please verify that {cmd_args_list[0]} is installed and in $PATH")
        exit(1)
    return output


class IBLink:
    def __init__(self, src, srcport, dst, dstport, speed):
        self.src = src
        self.srcport = srcport
        self.dst = dst
        self.dstport = dstport
        self.speed = speed


class _IBBase:
    def __init__(self, lid, name, guid):
        self.lid = lid
        self.name = name
        self.guid = guid
        self.links = {}

    def __str__(self):
        result = f"<{self.__class__.__name__}: '{self.name}' (lid {str(self.lid).rjust(3)} {self.guid})"
        return result

    def __repr__(self):
        return self.__str__()

class IBHost(_IBBase):
    def __init__(self, lid, name, guid, switch, switch_port, speed):
        self.switch = switch
        self.switch_port = switch_port
        self.speed = speed
        _IBBase.__init__(self, lid, name, guid)

    def __str__(self):
        result = _IBBase.__str__(self) + ">"
        return result


class IBSwitch(_IBBase):
    def __init__(self, lid, name, guid, portcount):
        self.portcount = portcount
        self.routes = {}
        self.routes_by_port = {}
        self.connections = {}
        self.isls = {}
        self.endpoints = {}
        _IBBase.__init__(self, lid, name, guid)

    def __str__(self):
        result = _IBBase.__str__(self) + " " + self.portcount + " ports>"
        return result

def switch_short_name(name):
    tmp = name.split(';')
    if len(tmp) > 1:
        tmp = tmp[1]
    else:
        tmp = tmp[0]
    tmp = tmp.split(':')[0]
    tmp2 = tmp.split('-')
    if tmp2[0] == 'ib' and len(tmp2) > 1:
        tmp2 = tmp2[1:]
    if len(tmp2) > 1:
        tmp2 = '-'.join(tmp2)
    tmp = tmp2
    if type(tmp) is list:
        tmp = tmp[0]
    return tmp

def short_speed_info(speedinfo):
    if speedinfo.replace(" ", "").find("4X25") > -1:
        return "100Gb"
    if speedinfo.replace(" ", "").find("4X14") > -1:
        return "56Gb"
    if speedinfo.replace(" ", "").find("4X10") > -1:
        return "40Gb"
    if speedinfo.replace(" ", "").find("4X2.5") > -1:
        return "10Gb"
    return speedinfo
    
def get_line_quoted_substrings(line):
    # assumes substring is double quoted
    return re.findall('\"(.*?)\"', line)

def get_hex_val(line):
    hexpattern = '(0x[0-9,a-f,A-f]*)'
    return re.search(hexpattern, line)

def get_hex_vals(line):
    hexpattern = '(0x[0-9,a-f,A-f]*)'
    return re.findall(hexpattern, line)

def cleanup_linkinfo_string(string):
    string = string.strip()
    string = re.sub(' +', ' ', string)
    string = re.sub(r'[\[] ]', '', string)
    string = re.sub(r'[(] [)]', '', string).strip()
    return string

def parse_linkinfo_line(line, switches, endpoints):
    # linkinfo line format:
    # srcguid(hex) "   srcname(possibly space padded)" srclid srcport[  ]  \
    # ==( < speed and port info >)==>  dstguid(hex) dstlid dstport[  ] "   dstname" ( )
    # initially implemented with regex re package - way too messy.  splits and partitions are cleaner
    # print(line)
    line = cleanup_linkinfo_string(line)
    # print(line)
    src, dst = line.split(")==>", 1)
    src, speedinfo = src.split("==(", 1)
    src = src.strip()
    speedinfo = speedinfo.strip().split(' Active')[0]
    dst = dst.strip()

    src_guid, src = src.split(' \"')
    src_name, src = src.strip().split('\" ')
    src_lid, src_port = src.split(" ")
    src_lid = int(src_lid)
    dst, dst_name = dst.split(' \"')
    dst_name, _ = dst_name.split('\"')
    dst_guid, dst_lid, dst_port = dst.split(" ")
    dst_lid = int(dst_lid)
    if src_lid in switches:
        if dst_lid in switches:
            switches[src_lid].connections[int(src_port)] = switches[dst_lid]
            switches[src_lid].isls[int(src_port)] = (switches[dst_lid], int(dst_port), speedinfo)
            switches[dst_lid].connections[int(dst_port)] = switches[src_lid]
            switches[dst_lid].isls[int(dst_port)] = (switches[src_lid], int(src_port), speedinfo)
        else:
            endpoint = IBHost(dst_lid, dst_name, dst_guid, switches[src_lid], int(src_port), speedinfo)
            switches[src_lid].connections[int(src_port)] = endpoint
            switches[src_lid].endpoints[int(src_port)] = endpoint
            endpoints[dst_lid] = endpoint
    else:
        print(f" non-switch as source in parse_linkinfo_line {line}")

def load_linkinfo_data(switches, link_info_file=None):
    endpoints = {}
    if link_info_file is not None and os.path.isfile(link_info_file):
        with open(link_info_file, 'r') as infile:
            lines = infile.readlines()
    else:
        cmd = ['iblinkinfo', '--switches-only', '-l']
        output = run_cmd(cmd)
        lines = output.splitlines()
    for line in lines:
        if not re.search("Active/ ", line):
            continue
        if not line.startswith("0x"):
            continue
        parse_linkinfo_line(line, switches, endpoints)
    return endpoints

def parse_route_line(line):
    # route file line format:
    # lid(hex) out-port ': (' <'Switch' | 'Channel Adapter' > 'portguid' guid(hex): <quoted name>')'
    hex_lid, rest = line.split(" ", 1)
    lid = int(hex_lid, 16)
    route_port, _ = rest.split(" ", 1)
    return [lid, int(route_port)]

def compute_route_info(switches, route_info_file=None):
    if route_info_file is not None and os.path.isfile(route_info_file):
        with open(route_info_file, 'r') as infile:
            lines = infile.readlines()
    else:
        lines = []
        for slid in switches.keys():
            cmd = ['ibroute', f"{slid}"]
            output = run_cmd(cmd)
            lines += output.splitlines()
    lid = -1
    for line in lines:
        if not line.startswith("0x"):
            if line.startswith("Unicast"):
                tmp = re.search('switch Lid ([0-9]*)', line).group(1)
                lid = int(tmp)
            continue
        route = parse_route_line(line)
        switches[lid].routes[route[0]] = route[1]
        if route[1] not in switches[lid].routes_by_port.keys():
            switches[lid].routes_by_port[route[1]] = [route[0]]
        else:
            switches[lid].routes_by_port[route[1]].append(route[0])

def get_switches(switch_info_file=None):
    if switch_info_file is not None and os.path.isfile(switch_info_file):
        with open(switch_info_file, 'r') as infile:
            lines = infile.readlines()
    else:
        cmd = ['ibswitches']
        output = run_cmd(cmd)
        lines = output.splitlines()

    result = {}
    for line in lines:
        if not line.startswith("Switch"):
            continue
        line = re.sub(' +', ' ', line)
        line = re.sub('\t', ' ', line)
        quoted_strings = re.findall(r'\"(.+?)\"', line)
        name = quoted_strings[0]
        if name is list:
            name = name[0]
        line = re.sub(r'\"(.+?)\"', 'nreplaced', line)
        line_items = line.split(" ")
        _, _, guid, _, portcount, _, _, _, _, _, lid, _, _ = line_items
        lid = int(lid)
        result[lid] = IBSwitch(lid, switch_short_name(name), guid, portcount)
    return result

def get_route(lid1, lid2, endports):
    next_switch = endports[lid1].switch
    lid1_port = endports[lid1].switch_port
    end_switch = endports[lid2].switch
    next_port = next_switch.routes[lid2]
    route = [(lid1, lid1_port), (next_switch.lid, next_port)]
    while next_switch != end_switch:
        next_switch = next_switch.connections[next_port]
        next_port = next_switch.routes[lid2]
        route.append((next_switch.lid, next_port))
    route.append(lid2)
    return route

def get_portstripped_hostname(hostname):
    stripped_name = hostname.split(" ", 1)[0]
    return stripped_name

def get_hostnames_list(all_switches, strip_port_name=True):
    resultlist = []
    for swlid, sw in all_switches:
        for swport, endpoint in sw.endpoints:
            if strip_port_name:
                stripped_name = endpoint.name.split(" ", 1)[0]
            else:
                stripped_name = endpoint.name
            if stripped_name not in resultlist:
                resultlist.append(stripped_name)
    return resultlist

def get_stripped_host_by_name_dict(all_switches):
    resultdict = {}
    for swlid, sw in all_switches:
        for swport, endpoint in sw.endpoints:
            host_name, port_name = endpoint.name.split(" ", 1)
            if host_name not in resultdict:
                resultdict[host_name] = [endpoint]
            else:
                resultdict[host_name].append(endpoint)
    return resultdict

def get_hostinfo_tables(all_endports):
    host_names_only = []
    host_lids = {}
    for k, v in all_endports.items():
        end_lid = k
        host_name, port_name = v.name.split(" ", 1)
        if host_name not in host_names_only:
            host_names_only.append(host_name)
        if host_name not in host_lids:
            host_lids[host_name] = [end_lid]
        else:
            host_lids[host_name].append(end_lid)
    return host_names_only, host_lids

def subroute_str(subroute, all_switches):
    ((s1, p1), (s2, p2)) = subroute
    return f"{all_switches[s1].name}({p1}) --> {all_switches[s2].name}({p2})"

def compute_subroutes(host1_lids, host2_lids, all_endports, all_switches):
    all_subroutes = {}
    for l1 in host1_lids:
        for l2 in host2_lids:
            route_forward = get_route(l1, l2, all_endports)
            pairs_f = list(zip(route_forward[1:-1], route_forward[2:-1]))
            # print(f"route from {l1} to {l2}: {route_forward}, subroute count: {len(all_subroutes)}")
            for subroute in pairs_f:
                subroute_s = subroute_str(subroute, all_switches)
                if subroute not in all_subroutes:
                    print(f"    New subroute {subroute_s}, in route from {l1} to {l2}; unique subroute count: {len(all_subroutes)}")
                    all_subroutes[subroute] = [(l1, l2)]
                elif (l1, l2) not in all_subroutes[subroute]:
                    # print(f"    shared subroute: {subroute_s} users: {all_subroutes[subroute]}")
                    all_subroutes[subroute].append((l1, l2))
                else:
                    # print(f"   {subroute_s} already used - users: {all_subroutes[subroute]}    (from {l1})")
                    # all_subroutes[subroute].append(l2)
                    pass
    return all_subroutes

def expand_hostnames(host, host_names_list=None):
    if host_names_list is None:
        host_names_list = get_hostnames_list(strip_port_name=True)
    if not isinstance(host, list):
        host = [host]
    result = []
    for hostpattern in host:
        for h in host_names_list:
            if h.startswith(hostpattern):
                result.append(h)
    return result

def get_all_host_lids(host_lids, hosts):
    result = []
    for h in hosts:
        for hl in host_lids[h]:
            result.append(hl)
    return result

def print_switch_information(all_switches):
    for key, val in all_switches.items():
        print(f"Switch {val} - {len(val.routes)} route entries.")
        print(f"    Connection count: {len(val.connections)}; "
              f"{len(val.isls)} ISLs, {len(val.connections) - len(val.isls)} endpoints")
        print(f"        ISLs for switch {val}:")
        for p, (sw, swp, speed) in val.isls.items():
            print(f"            from port {p:3} to: port {swp:3} on switch {sw.name}"
                  f" (lid {sw.lid:3} {sw.guid}) speed {speed}")
            rs = [r for r in val.routes_by_port[p] if r not in all_switches.keys()]
            print(f"                routes to endport lids: {rs}")
        print(f"        Endpoints for switch {val}:")
        for p, val2 in val.connections.items():
            if val2.lid not in all_switches:
                print(f"            port {p:3}: '{val2.name}'{' '.ljust(32 - len(val2.name))} "
                      f"(lid {val2.lid:3} {val2.guid}) speed {val2.speed}")
        print()

def print_shared_subroutes(all_switches, all_subroutes, all_endports):
    for subroute, used_by in all_subroutes.items():
        if len(used_by) > 1:
            (s1, p1), (s2, p2) = subroute
            s1name = all_switches[s1].name
            s2name = all_switches[s2].name
            print(f"    {len(used_by)} routes use ISL from switch '{s1name}'({s1}) p{p1}"
                  f" to switch '{s2name}'({s2}) p{p2}: ")
            for s, d in used_by:
                # print(f"            route '{all_endports[s].name}' -> '{all_endports[d].name}'")
                pass

def print_route_tracing_message(host1_lids, host1_exp, host2_lids, host2_exp, parsed_args):
    if len(host1_lids) == 0 or len(host2_lids) == 0:
        print(f"*** Error: args {parsed_args.starthost}:{host1_exp}, "
              f" {parsed_args.otherhosts}:{host2_exp}"
              f"- not enough valid hosts found for route tracing.  Skipping.")
        return
    print(f"\n    Computing routing usage between (expanded hosts) {host1_exp}\nand\n{host2_exp}")
    # print(f"        lids: {host1_lids} and {host2_lids}")

def print_switches(all_switches):
    print(f"--- Switches ({len(all_switches)} found): ")
    for k, s in all_switches.items():
        print(f"   {k:3}: {s}")

def print_endports(all_endports):
    print(f"--- Endpoints ({len(all_endports)} found):")
    for k, v in all_endports.items():
        print(f"    '{v.name}'{' '.ljust(32-len(v.name))} lid {k:3} on switch {v.switch} port {v.switch_port}")

def do_diag_run(parsed_args):
    all_switches = get_switches(parsed_args.switch_info_file)
    print_switches(all_switches)
    compute_route_info(all_switches, parsed_args.route_info_file)
    print(f"\n    Finding switch connections...\n")
    all_endports = load_linkinfo_data(all_switches, parsed_args.link_info_file)
    print_endports(all_endports)
    print(f"\n--- Switch information:")
    print_switch_information(all_switches)
    host_names_only, host_lids = get_hostinfo_tables(all_endports)
    print(f"--- Hosts:")
    print(f"{len(host_lids)} port-consolidated hosts found (assumes hostname<space><portname> format for endport):")
    for hname, lids in host_lids.items():
        print(f"    {hname} {' '.ljust(32 - len(hname))} lids: {lids}")
    print(f"\n--- Route contention: (computing between: {parsed_args.starthost} and {parsed_args.otherhosts})")
    host1_exp = expand_hostnames(parsed_args.starthost, host_names_list=host_names_only)
    host1_lids = get_all_host_lids(host_lids, host1_exp)
    host2_exp = expand_hostnames(parsed_args.otherhosts, host_names_list=host_names_only)
    host2_lids = get_all_host_lids(host_lids, host2_exp)
    print_route_tracing_message(host1_lids, host1_exp, host2_lids, host2_exp, parsed_args)
    all_subroutes = compute_subroutes(host1_lids, host2_lids, all_endports, all_switches)
    print(f"\n    Finding and printing shared ISLs for routes...\n")
    print_shared_subroutes(all_switches, all_subroutes, all_endports)
    print(f"\n    Computing routing usage between (expanded hosts) {host1_exp} and {host2_exp}")
    print(f"\n        lids: {host2_lids} and {host1_lids}")
    all_subroutes = compute_subroutes(host2_lids, host1_lids, all_endports, all_switches)
    print(f"\n    Finding and printing shared ISLs for routes...\n")
    print_shared_subroutes(all_switches, all_subroutes, all_endports)
    print("Done.")
    return all_switches

def main():
    time_a = time.time()
    args = get_args()
    do_diag_run(args)
    time_c = time.time()
    print(f"run took: {time_c - time_a}")

if __name__ == '__main__':
    if len(sys.argv) == 1:
        sys.argv = [sys.argv[0], "cn", "weka",
                    "--switch_info_file", "uconn-ib/uconn-ib-switches.txt", 
                    "--route_info_file", "uconn-ib/uconn-ib-routes.txt",
                    "--link_info_file", "uconn-ib/uconn-ib-links.txt"
        ]
    main()

