import ibdiag
import time
import sys
import xlsxwriter
import xlsxwriter.worksheet    
import argparse

class IBWorksheet(xlsxwriter.worksheet.Worksheet):
    def __init__(self):
        super().__init__()
        self.next_row = 0
    
    def write_next_row(self, data, cell_format = None):
        self.write_row(self.next_row, 0, data, cell_format=cell_format)
        self.next_row += 1

    def set_column_widths(self, widths_list):
        for i, w in enumerate(widths_list):
            self.set_column(i, i, w)

class IBWorkbook(xlsxwriter.Workbook):
    def __init__(self, filename):
        xlsxwriter.Workbook.__init__(self, filename)
        self.bold = self.add_format()
        self.bold.set_bold()
        self.sheets = {}

    def add_worksheets(self, name_tab_tuples):
        for name, tab in name_tab_tuples:
            self.sheets[name] = self.add_worksheet(name=tab, worksheet_class=IBWorksheet)

def open_xlsx(outfile):
    wb = IBWorkbook(outfile)
    wb.add_worksheets([('switches', 'Switches'), ('sw_ports', 'All Up Ports'), ('isls', 'ISLs'), 
        ('endpoints', 'Endpoints'), ('routes', 'Routes'), ('downports', 'Down Ports'),
        ('lidroutes', 'Routes by Lid')])

    wb.sheets['switches'].write_next_row(["Switch Name", "Switch LID", "# Ports", "# ISLs", "# Endpoints"], wb.bold)
    wb.sheets['switches'].set_column_widths([30, 8, 7, 7, 11])
    wb.sheets['sw_ports'].write_next_row(["Switch Name", "Switch LID", "Switch Port", "Connected Name", "Connected Lid"], wb.bold)
    wb.sheets['sw_ports'].set_column_widths([30, 8, 10, 30, 12])
    wb.sheets['endpoints'].write_next_row(["Switch Name", "Switch LID", "Switch Port", "Endpoint name", "Endpoint Lid", "Speed"], wb.bold)
    wb.sheets['endpoints'].set_column_widths([30, 8, 10, 30, 10, 8])
    wb.sheets['isls'].write_next_row(["Switch Name", "Switch LID", "Switch Port", "Dest Switch", "Dest Lid", "Dest Port", "Speed"], wb.bold)
    wb.sheets['isls'].set_column_widths([30, 8, 10, 30, 8, 10, 8])
    wb.sheets['downports'].write_next_row(["Switch Name", "Switch LID", "Switch Port"], wb.bold)
    wb.sheets['downports'].set_column_widths([30, 8, 10, 2, 2])
    wb.sheets['routes'].write_next_row(["Switch Name", "Switch LID", "Switch Port", "# LID Routes", "LIDs Routed via this port"], wb.bold)
    wb.sheets['routes'].set_column_widths([30, 8, 10, 10, 100])
    wb.sheets['lidroutes'].write_next_row(["Endpoint Name", "Endpoint LID", "Exits via port", "on Switch"], wb.bold)
    wb.sheets['lidroutes'].set_column_widths([30, 20, 20, 20, 20])
    return wb

def write_xlsx(switches, endpoints, outfile):
    wb = open_xlsx(outfile)
    for switchnum, (k, s) in enumerate(switches.items()):
        switchpp = f"{s.name} ({s.lid})"
        wb.sheets['switches'].write_next_row([switchpp, s.lid, int(s.portcount), len(s.isls), len(s.endpoints)])
        for portnum in range(0, int(s.portcount)):
            if portnum in s.connections.keys():
                dest_lid = s.connections[portnum].lid
                dest_name = s.connections[portnum].name
                if dest_lid in switches.keys():
                    dest_name = f"{dest_name} ({dest_lid})"
                wb.sheets['sw_ports'].write_next_row([switchpp, s.lid, portnum, dest_name, dest_lid])
                if dest_lid in switches.keys():
                    _, port, speedinfo = s.isls[portnum]
                    speedinfo = ibdiag.short_speed_info(speedinfo)
                    wb.sheets['isls'].write_next_row([switchpp, s.lid, portnum, dest_name, dest_lid, port, speedinfo])
                    if portnum in s.routes_by_port.keys():
                        wb.sheets['routes'].write_next_row([switchpp, s.lid, portnum, len(s.routes_by_port[portnum]), 
                            ' '.join(str(r) for r in s.routes_by_port[portnum])])
                else:
                    speedinfo = s.endpoints[portnum].speed
                    speedinfo = ibdiag.short_speed_info(speedinfo)
                    wb.sheets['endpoints'].write_next_row([switchpp, s.lid, portnum, dest_name, dest_lid, speedinfo])
                if portnum in s.routes_by_port.keys():
                    for r in s.routes_by_port[portnum]:
                        if r in endpoints.keys():
                            name = endpoints[r].name
                            wb.sheets['lidroutes'].write_next_row([name, r, portnum, switchpp])
            else:
                wb.sheets['downports'].write_next_row([switchpp, s.lid, portnum])
    wb.close()

def get_arg_parser(description="ibdiag_xlsx: Generate IB excel data file"):
    my_parser = ibdiag.get_arg_parser(description=description)
    my_parser.add_argument("--xlsx_file", dest="xlsx_file", default="ibdiag.xlsx",
                           help="file name for .xlsx output file")
    return my_parser

def get_args(allow_unknown_args=False):
    my_parser = get_arg_parser()
    a = my_parser.parse_args()
    return a

def main():
    time_a = time.time()
    args = get_args()
    switches, endpoints = ibdiag.do_diag_run(args)
    write_xlsx(switches, endpoints, args.xlsx_file)
    time_c = time.time()
    print(f"run took: {time_c - time_a}")

def use_ucon_sample_data():
    if len(sys.argv) == 1:
        datadir = ibdiag.use_ucon_sample_data()
        ibdiag.add_argv_arg("--xlsx_file", datadir + "ucon.xlsx")
        return datadir

def use_peng_sample_data():
    if len(sys.argv) == 1:
        datadir = ibdiag.use_peng_sample_data()
        ibdiag.add_argv_arg("--xlsx_file", datadir + "peng.xlsx")
        return datadir

if __name__ == '__main__':
    # use_ucon_sample_data()
    # use_peng_sample_data()
    main()
