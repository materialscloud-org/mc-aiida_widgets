"""Widgets that allow to query online databases."""
import ipywidgets as ipw
from traitlets import Instance, Bool, default, dlink
from ase import Atoms

from aiida.tools.dbimporters.plugins.cod import CodDbImporter


class CodQueryWidget(ipw.VBox):
    '''Query structures in Crystallography Open Database (COD)
    Useful class members:
    :ivar structure(Atoms): trait that contains the selected structure, None if structure is not selected.'''

    structure = Instance(Atoms, allow_none=True)
    disabled = Bool()

    def __init__(self, **kwargs):
        description = ipw.HTML("""<h3>Get crystal structures from
    <a href="http://www.crystallography.net">Crystallography Open Database</a></h3>
    <b>Queries by formula</b>
    <br>
    For the queries by formula please adhere to the Hill notation.
    The chemical symbol of an element should be followed by its number in the structure,
    except when there is only one atom.
    When the structure does NOT contain carbon atoms, all the elements are listed alphabetically.
    Example: <i>O2 Si</i>.
    <br>
    In case the structure DOES contain carbon atoms its number following the 'C' symbol is indicated first.
    If hydrogen is also present in the structure then 'H' symbol and its number is indicated second.
    The remaining elements are listed in the alphabetical order. Example: <i>C H4 N2 O</i>.
    <br>
    <b>Queries by the structure id number</b>
    <br>
    For the queries by structure id, plese provide the database id number. Example: <i>1008786</i>
    """)
        layout = ipw.Layout(width="400px")
        style = {"description_width": "initial"}
        self.inp_elements = ipw.Text(description="",
                                     value="",
                                     placeholder='e.g.: Ni Ti or id number',
                                     layout=layout,
                                     style=style)
        self.btn_query = ipw.Button(description='Query')
        dlink((self, 'disabled'), (self.btn_query, 'disabled'))

        self.query_message = ipw.HTML("Waiting for input...")
        self.drop_structure = ipw.Dropdown(description="",
                                           options=[("select structure", {
                                               "status": False
                                           })],
                                           style=style,
                                           layout=layout)
        dlink((self, 'disabled'), (self.drop_structure, 'disabled'))

        self.link = ipw.HTML("Link to the web-page will appear here")
        self.btn_query.on_click(self._on_click_query)
        self.drop_structure.observe(self._on_select_structure, names=['value'])

        children = [
            description,
            ipw.HBox([self.btn_query, self.inp_elements]), self.query_message,
            ipw.HBox([self.drop_structure, self.link])
        ]
        super(CodQueryWidget, self).__init__(children=children, **kwargs)

    @staticmethod
    def _query(idn=None, formula=None):
        """Make the actual query."""
        importer = CodDbImporter()
        if idn is not None:
            return importer.query(id=idn)
        if formula is not None:
            return importer.query(formula=formula)
        return None

    def _on_click_query(self, change):  # pylint: disable=unused-argument
        """Call query when the corresponding button is pressed."""
        structures = [("select structure", {"status": False})]
        idn = None
        formula = None
        self.query_message.value = "Quering the database ... "
        try:
            idn = int(self.inp_elements.value)
        except ValueError:
            formula = str(self.inp_elements.value)

        for entry in self._query(idn=idn, formula=formula):
            try:
                entry_cif = entry.get_cif_node()
                formula = entry_cif.get_ase().get_chemical_formula()
            except:  # pylint: disable=bare-except
                continue
            entry_add = ("{} (id: {})".format(formula, entry.source['id']), {
                "status": True,
                "cif": entry_cif,
                "url": entry.source['uri'],
                "id": entry.source['id'],
            })
            structures.append(entry_add)

        self.query_message.value += "{} structures found".format(len(structures) - 1)
        self.drop_structure.options = structures

    def _on_select_structure(self, change):
        """When a structure was selected."""
        selected = change['new']
        if selected['status'] is False:
            self.structure = None
            return
        self.structure = selected['cif'].get_ase()
        struct_url = selected['url'].split('.cif')[0] + '.html'
        self.link.value = '<a href="{}" target="_blank">COD entry {}</a>'.format(struct_url, selected['id'])

    @default('structure')
    def _default_structure(self):  # pylint: disable=no-self-use
        return None
