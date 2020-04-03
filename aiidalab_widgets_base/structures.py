"""Module to provide functionality to import structures."""
# pylint: disable=no-self-use

import os
import tempfile
import datetime
from collections import OrderedDict
import numpy as np
import ipywidgets as ipw
from traitlets import Instance, Unicode, Union, link, default, observe, validate

# ASE imports
from ase import Atom, Atoms
from ase.data import chemical_symbols

# AiiDA and AiiDA lab imports
from aiida.orm import CalcFunctionNode, CalcJobNode, Data, QueryBuilder, Node, WorkChainNode
from aiida.plugins import DataFactory
from .utils import get_ase_from_file
from .viewers import StructureDataViewer


class StructureManagerWidget(ipw.VBox):
    '''Upload a structure and store it in AiiDA database.

    Attributes:
        structure(Atoms): trait that contains the selected structure. 'None' if no structure is selected.
        structure_node(StructureData, CifData): trait that contains AiiDA structure object
        node_class(str): trait that contains structure_node type (as string).
    '''

    structure = Union([Instance(Atoms), Instance(Data)], allow_none=True)
    structure_node = Instance(Data, allow_none=True, read_only=True)
    node_class = Unicode()

    SUPPORTED_DATA_FORMATS = {'CifData': 'cif', 'StructureData': 'structure'}

    def __init__(self, importers, storable=True, node_class=None, **kwargs):
        """
        Arguments:
            importers(list): list of tuples each containing the displayed name of importer and the
                importer object. Each object should containt 'structure' trait pointing to the imported
                structure. The trait will be linked to 'structure' trait of this class.

            storable(bool): Whether to provide Store button (together with Store format)

            node_class(str): AiiDA node class for storing the structure.
                Possible values: 'StructureData', 'CifData' or None (let the user decide).
                Note: If your workflows require a specific node class, better fix it here.
        """

        # Make sure the list is not empty
        if not importers:
            raise ValueError("The parameter importers should contain a list (or tuple) of tuples "
                             "(\"importer name\", importer), got a falsy object.")

        # Store button.
        self.btn_store = ipw.Button(description='Store in AiiDA', disabled=True)
        self.btn_store.on_click(self._on_click_store)

        # Setting traits' initial values
        self._inserted_structure = None

        # Structure viewer.
        self.viewer = StructureDataViewer(downloadable=False)
        link((self, 'structure'), (self.viewer, 'structure'))

        # Store format selector.
        data_format = ipw.RadioButtons(options=self.SUPPORTED_DATA_FORMATS, description='Data type:')
        link((data_format, 'label'), (self, 'node_class'))

        # Description that is stored along with the new structure.
        self.structure_description = ipw.Text(placeholder="Description (optional)")

        # Displaying structure importers.
        if len(importers) == 1:
            # If there is only one importer - no need to make tabs.
            self._structure_sources_tab = importers[0][1]
            # Assigning a function which will be called when importer provides a structure.
            link((self, 'structure'), (importers[0][1], 'structure'))
        else:
            self._structure_sources_tab = ipw.Tab()  # Tabs.
            self._structure_sources_tab.children = [i[1] for i in importers]  # One importer per tab.
            for i, (label, importer) in enumerate(importers):
                # Labeling tabs.
                self._structure_sources_tab.set_title(i, label)
                link((self, 'structure'), (importer, 'structure'))

        # Store button, store class selector, description.
        store_and_description = []

        if storable:
            store_and_description.append(self.btn_store)
        if node_class is None:
            store_and_description.append(data_format)
        elif node_class in self.SUPPORTED_DATA_FORMATS:
            self.node_class = node_class
        else:
            raise ValueError("Unknown data format '{}'. Options: {}".format(node_class,
                                                                            list(self.SUPPORTED_DATA_FORMATS.keys())))
        self.output = ipw.HTML('')

        store_and_description.append(self.structure_description)
        store_and_description = ipw.HBox(store_and_description)

        super().__init__(children=[self._structure_sources_tab, self.viewer, store_and_description, self.output],
                         **kwargs)

    def _on_click_store(self, change):  # pylint: disable=unused-argument
        self.store_structure()

    def store_structure(self, label=None, description=None):
        """Stores the structure in AiiDA database."""

        if self.structure_node is None:
            return
        if self.structure_node.is_stored:
            self.output.value = "Already stored in AiiDA [{}], skipping...".format(self.structure_node)
            return
        if label:
            self.structure_node.label = label
        if description:
            self.structure_node.description = description
        self.structure_node.store()
        self.output.value = "Stored in AiiDA [{}]".format(self.structure_node)

    @staticmethod
    @default('node_class')
    def _default_node_class():
        return 'StructureData'

    @observe('node_class')
    def _change_structure_node(self, _=None):
        self._structure_changed()

    @default('structure')
    def _default_structure(self):
        return None

    @validate('structure')
    def _valid_structure(self, change):
        """Returns ASE atoms object and sets structure_node trait."""

        self._inserted_structure = change['value']

        # If structure trait is set to Atoms object, structure node must be generated
        if isinstance(self._inserted_structure, Atoms):
            return self._inserted_structure

        # If structure trait is set to AiiDA node, converting it to ASE Atoms object
        if isinstance(self._inserted_structure, Data):
            return self._inserted_structure.get_ase()

        return None

    @observe('structure')
    def _structure_changed(self, _=None):
        """Perform some operations that depend on the value of `structure` trait.

        This function enables/disables `btn_store` widget if structure is provided/set to None.
        Also, the function sets `structure_node` trait to the selected node type.
        """

        # If structure trait was set to None, structure_node should become None as well.
        if self.structure is None:
            self.set_trait('structure_node', None)
            self.btn_store.disabled = True
            return

        self.btn_store.disabled = False

        # Chosing type for the structure node.
        StructureNode = DataFactory(self.SUPPORTED_DATA_FORMATS[self.node_class])  # pylint: disable=invalid-name

        # If structure trait is set to Atoms object, structure node must be created from it.
        if isinstance(self._inserted_structure, Atoms):
            structure_node = StructureNode(ase=self._inserted_structure)

        # If structure trait is set to AiiDA node, converting it to ASE Atoms object
        elif isinstance(self._inserted_structure, Data):

            # Transform the structure to the StructureNode if needed.
            if isinstance(self._inserted_structure, StructureNode):
                structure_node = self._inserted_structure

            else:
                # self.structure was already converted to ASE Atoms object.
                structure_node = StructureNode(ase=self.structure)

        # Setting the structure_node trait.
        self.set_trait('structure_node', structure_node)
        self.structure_node.description = self.structure_description.value
        self.structure_node.label = self.structure.get_chemical_formula()

    @default('structure_node')
    def _default_structure_node(self):
        return None


class StructureUploadWidget(ipw.VBox):
    """Class that allows to upload structures from user's computer."""
    structure = Instance(Atoms, allow_none=True)

    def __init__(self, text="Upload Structure"):
        self.file_path = None
        self.file_upload = ipw.FileUpload(description=text, layout=ipw.Layout(width='200px'))
        supported_formats = ipw.HTML(
            """<a href="https://wiki.fysik.dtu.dk/ase/_modules/ase/io/formats.html" target="_blank">
        Supported structure formats
        </a>""")
        self.file_upload.observe(self._on_file_upload, names='value')
        super().__init__(children=[self.file_upload, supported_formats])

    def _on_file_upload(self, change):  # pylint: disable=unused-argument
        """When file upload button is pressed."""
        assert change['name'] == 'value'
        assert len(change['new']) == 1

        new_file = list(change['new'].values())[0]
        filename = new_file['metadata']['name']
        content = new_file['content']

        self.file_path = os.path.join(tempfile.mkdtemp(), filename)
        with open(self.file_path, 'wb') as fobj:
            fobj.write(content)
        self.structure = get_ase_from_file(self.file_path)

    @default('structure')
    def _default_structure(self):
        return None


class StructureExamplesWidget(ipw.VBox):
    """Class to provide example structures for selection."""
    structure = Instance(Atoms, allow_none=True)

    def __init__(self, examples, **kwargs):
        self.on_structure_selection = lambda structure_ase, name: None
        self._select_structure = ipw.Dropdown(options=self.get_example_structures(examples))
        self._select_structure.observe(self._on_select_structure, names=['value'])
        super().__init__(children=[self._select_structure], **kwargs)

    @staticmethod
    def get_example_structures(examples):
        """Get the list of example structures."""
        if not isinstance(examples, list):
            raise ValueError("parameter examples should be of type list, {} given".format(type(examples)))
        return [("Select structure", False)] + examples

    def _on_select_structure(self, change):  # pylint: disable=unused-argument
        """When structure is selected."""

        self.structure = get_ase_from_file(self._select_structure.value) if self._select_structure.value else None

    @default('structure')
    def _default_structure(self):
        return None


class StructureBrowserWidget(ipw.VBox):
    """Class to query for structures stored in the AiiDA database."""
    structure = Union([Instance(Atoms), Instance(Data)], allow_none=True)

    def __init__(self):

        # Structure objects we want to query for.
        self.query_structure_type = (DataFactory('structure'), DataFactory('cif'))

        # Extracting available process labels.
        qbuilder = QueryBuilder().append((CalcJobNode, WorkChainNode), project="label")
        self.drop_label = ipw.Dropdown(options=sorted({'All'}.union({i[0] for i in qbuilder.iterall() if i[0]})),
                                       value='All',
                                       description='Process Label',
                                       disabled=True,
                                       style={'description_width': '120px'},
                                       layout={'width': '50%'})
        self.drop_label.observe(self.search, names='value')

        # Disable process labels selection if we are not looking for the calculated structures.
        def disable_drop_label(change):
            self.drop_label.disabled = not change['new'] == 'calculated'

        # Select structures kind.
        self.mode = ipw.RadioButtons(options=['all', 'uploaded', 'edited', 'calculated'], layout={'width': '25%'})
        self.mode.observe(self.search, names='value')
        self.mode.observe(disable_drop_label, names='value')

        # Date range.
        # Note: there is Date picker widget, but it currently does not work in Safari:
        # https://ipywidgets.readthedocs.io/en/latest/examples/Widget%20List.html#Date-picker
        date_text = ipw.HTML(value='<p>Select the date range:</p>')
        self.start_date_widget = ipw.Text(value='', description='From: ', style={'description_width': '120px'})
        self.end_date_widget = ipw.Text(value='', description='To: ')

        # Search button.
        btn_search = ipw.Button(description='Search',
                                button_style='info',
                                layout={
                                    'width': 'initial',
                                    'margin': '2px 0 0 2em'
                                })
        btn_search.on_click(self.search)

        age_selection = ipw.VBox(
            [date_text, ipw.HBox([self.start_date_widget, self.end_date_widget, btn_search])],
            layout={
                'border': '1px solid #fafafa',
                'padding': '1em'
            })

        h_line = ipw.HTML('<hr>')
        box = ipw.VBox([age_selection, h_line, ipw.HBox([self.mode, self.drop_label])])

        self.results = ipw.Dropdown(layout={'width': '900px'})
        self.results.observe(self._on_select_structure)
        self.search()
        super().__init__([box, h_line, self.results])

    def preprocess(self):
        """Search structures in AiiDA database and add formula extra to them."""

        queryb = QueryBuilder()
        queryb.append(self.query_structure_type, filters={'extras': {'!has_key': 'formula'}})
        for item in queryb.all():  # iterall() would interfere with set_extra()
            try:
                formula = item[0].get_formula()
            except AttributeError:
                # Slow part.
                formula = item[0].get_ase().get_chemical_formula()
            item[0].set_extra("formula", formula)

    def search(self, _=None):
        """Launch the search of structures in AiiDA database."""
        self.preprocess()

        qbuild = QueryBuilder()

        # If the date range is valid, use it for the search
        try:
            start_date = datetime.datetime.strptime(self.start_date_widget.value, '%Y-%m-%d')
            end_date = datetime.datetime.strptime(self.end_date_widget.value, '%Y-%m-%d') + datetime.timedelta(hours=24)

        # Otherwise revert to the standard (i.e. last 7 days)
        except ValueError:
            start_date = datetime.datetime.now() - datetime.timedelta(days=7)
            end_date = datetime.datetime.now() + datetime.timedelta(hours=24)

            self.start_date_widget.value = start_date.strftime('%Y-%m-%d')
            self.end_date_widget.value = end_date.strftime('%Y-%m-%d')

        filters = {}
        filters['ctime'] = {'and': [{'>': start_date}, {'<=': end_date}]}

        if self.mode.value == "uploaded":
            qbuild2 = QueryBuilder().append(self.query_structure_type, project=["id"],
                                            tag='structures').append(Node, with_outgoing='structures')
            processed_nodes = [n[0] for n in qbuild2.all()]
            if processed_nodes:
                filters['id'] = {"!in": processed_nodes}
            qbuild.append(self.query_structure_type, filters=filters)

        elif self.mode.value == "calculated":
            if self.drop_label.value == 'All':
                qbuild.append((CalcJobNode, WorkChainNode), tag='calcjobworkchain')
            else:
                qbuild.append((CalcJobNode, WorkChainNode),
                              filters={'label': self.drop_label.value},
                              tag='calcjobworkchain')
            qbuild.append(self.query_structure_type, with_incoming='calcjobworkchain', filters=filters)

        elif self.mode.value == "edited":
            qbuild.append(CalcFunctionNode)
            qbuild.append(self.query_structure_type, with_incoming=CalcFunctionNode, filters=filters)

        elif self.mode.value == "all":
            qbuild.append(self.query_structure_type, filters=filters)

        qbuild.order_by({self.query_structure_type: {'ctime': 'desc'}})
        matches = {n[0] for n in qbuild.iterall()}
        matches = sorted(matches, reverse=True, key=lambda n: n.ctime)

        options = OrderedDict()
        options["Select a Structure ({} found)".format(len(matches))] = False

        for mch in matches:
            label = "PK: {}".format(mch.id)
            label += " | " + mch.ctime.strftime("%Y-%m-%d %H:%M")
            label += " | " + mch.get_extra("formula")
            label += " | " + mch.node_type.split('.')[-2]
            label += " | " + mch.description
            options[label] = mch

        self.results.options = options

    def _on_select_structure(self, _=None):
        self.structure = self.results.value or None

    @default('structure')
    def _default_structure(self):
        return None


class SmilesWidget(ipw.VBox):
    """Conver SMILES into 3D structure."""
    structure = Instance(Atoms, allow_none=True)

    SPINNER = """<i class="fa fa-spinner fa-pulse" style="color:red;" ></i>"""

    def __init__(self):
        try:
            import openbabel  # pylint: disable=unused-import
        except ImportError:
            super().__init__(
                [ipw.HTML("The SmilesWidget requires the OpenBabel library, "
                          "but the library was not found.")])
            return

        self.smiles = ipw.Text()
        self.create_structure_btn = ipw.Button(description="Generate molecule", button_style='info')
        self.create_structure_btn.on_click(self._on_button_pressed)
        self.output = ipw.HTML("")
        super().__init__([self.smiles, self.create_structure_btn, self.output])

    @staticmethod
    def pymol_2_ase(pymol):
        """Convert pymol object into ASE Atoms."""

        asemol = Atoms()
        for atm in pymol.atoms:
            asemol.append(Atom(chemical_symbols[atm.atomicnum], atm.coords))
        asemol.cell = np.amax(asemol.positions, axis=0) - np.amin(asemol.positions, axis=0) + [10] * 3
        asemol.pbc = True
        asemol.center()
        return asemol

    def _optimize_mol(self, mol):
        """Optimize a molecule using force field (needed for complex SMILES)."""

        # Note, the pybel module imported below comes together with openbabel package. Do not confuse it with
        # pybel package available on PyPi: https://pypi.org/project/pybel/
        import pybel  # pylint:disable=import-error

        self.output.value = "Screening possible conformers {}".format(self.SPINNER)  #font-size:20em;

        f_f = pybel._forcefields["mmff94"]  # pylint: disable=protected-access
        if not f_f.Setup(mol.OBMol):
            f_f = pybel._forcefields["uff"]  # pylint: disable=protected-access
            if not f_f.Setup(mol.OBMol):
                self.output.value = "Cannot set up forcefield"
                return

        # initial cleanup before the weighted search
        f_f.SteepestDescent(5500, 1.0e-9)
        f_f.WeightedRotorSearch(15000, 500)
        f_f.ConjugateGradients(6500, 1.0e-10)
        f_f.GetCoordinates(mol.OBMol)
        self.output.value = ""

    def _on_button_pressed(self, change):  # pylint: disable=unused-argument
        """Convert SMILES to ase structure when button is pressed."""
        self.output.value = ""

        # Note, the pybel module imported below comes together with openbabel package. Do not confuse it with
        # pybel package available on PyPi: https://pypi.org/project/pybel/
        import pybel  # pylint:disable=import-error

        if not self.smiles.value:
            return

        mol = pybel.readstring("smi", self.smiles.value)
        self.output.value = """SMILES to 3D conversion {}""".format(self.SPINNER)
        mol.make3D()

        pybel._builder.Build(mol.OBMol)  # pylint: disable=protected-access
        mol.addh()
        self._optimize_mol(mol)
        self.structure = self.pymol_2_ase(mol)

    @default('structure')
    def _default_structure(self):
        return None
