from __future__ import print_function
import ipywidgets as ipw

from aiida.tools.dbimporters.plugins.cod import CodDbImporter

class CodQueryWidget(ipw.VBox):
    '''Query structures in Crystallography Open Database (COD)
    Useful class members:
    :ivar has_structure: link to a method to be overloaded. It is called evey time when `self.drop_structure`
    widget has changed its name
    :vartype has_structure: function
    '''

    def __init__(self, **kwargs):
        description = ipw.HTML("""<b>For the queries please adhere to the Hill notation:</b>
    <br>
    Number of carbon atoms in a molecule is indicated first, the number of hydrogen atoms next, 
    and then the number of all other chemical elements subsequently, in alphabetical order of the
    chemical symbols. When the formula contains no carbon, all the elements, including hydrogen, 
    are listed alphabetically.""")
        layout = ipw.Layout(width="400px")
        style = {"description_width":"initial"}
        self.inp_elements = ipw.Text(description="", value="", placeholder='e.g.: Ni Ti or id number', layout=layout, style=style)
        self.btn_query = ipw.Button(description='Query in CoD')
        self.query_message = ipw.HTML("Waiting for input...")
        self.drop_structure = ipw.Dropdown(description="", options=[("select structure",{"status":False})],
                                           style=style, layout=layout )
        self.link = ipw.HTML("Link to the web-page will appear here")
        self.structure_ase = None

        self.btn_query.on_click(self._on_click_query)
        self.drop_structure.observe(self._on_select_structure, names=['value'])

        children = [description,
                    ipw.HBox([self.btn_query, self.inp_elements]),
                    self.query_message,
                    ipw.HBox([self.drop_structure, self.link])]
        super(CodQueryWidget, self).__init__(children=children, **kwargs)

    def _query(self, idn=None,formula=None):
        importer = CodDbImporter()
        if idn is not None:
            return importer.query(id=idn)
        elif formula is not None:
            return importer.query(formula=formula)

    def _on_click_query(self, change):
        structures = [("select structure", {"status":False})]
        idn = None
        formula = None
        self.query_message.value = "Quering the database ... "
        try: 
            idn = int(self.inp_elements.value)
        except:
            formula = str(self.inp_elements.value)

        for entry in self._query(idn=idn, formula=formula):
            try:
                entry_cif = entry.get_cif_node()
                formula = entry_cif.get_ase().get_chemical_formula()
            except:
                continue
            entry_add = ("{} (id: {})".format(formula, entry.source['id']),
                            {
                                "status": True,
                                "cif": entry_cif,
                                "url": entry.source['uri'],
                                "id": entry.source['id'],
                            }
                        )
            structures.append(entry_add)

        self.query_message.value += "{} structures found".format(len(structures)-1)
        self.drop_structure.options = structures

    def _on_select_structure(self, change):
        selected = change['new']
        if selected['status'] is False:
            self.structure_ase = None
            return
        self.structure_ase = selected['cif'].get_ase()
        formula = self.structure_ase.get_chemical_formula()
        struct_url = selected['url'].split('.cif')[0]+'.html'
        self.link.value='<a href="{}" target="_blank">COD entry {}</a>'.format(struct_url, selected['id'])
        if not self.on_structure_selection is None:
            self.on_structure_selection(structure_ase=self.structure_ase, name=formula)

    def on_structure_selection(self, structure_ase=None, name=None):
        pass