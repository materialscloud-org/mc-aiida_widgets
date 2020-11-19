"""Widgets that allow to query online databases."""
import requests
import ipywidgets as ipw
from traitlets import Bool, Float, Instance, Int, Unicode, default, validate
from ase import Atoms

from optimade_client.query_filter import OptimadeQueryFilterWidget
from optimade_client.query_provider import OptimadeQueryProviderWidget

from aiida.tools.dbimporters.plugins.cod import CodDbImporter


class CodQueryWidget(ipw.VBox):
    '''Query structures in Crystallography Open Database (COD)
    Useful class members:
    :ivar structure(Atoms): trait that contains the selected structure, None if structure is not selected.'''

    structure = Instance(Atoms, allow_none=True)

    def __init__(self, title='', **kwargs):
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
        self.title = title
        layout = ipw.Layout(width="400px")
        style = {"description_width": "initial"}
        self.inp_elements = ipw.Text(description="",
                                     value="",
                                     placeholder='e.g.: Ni Ti or id number',
                                     layout=layout,
                                     style=style)
        self.btn_query = ipw.Button(description='Query')
        self.query_message = ipw.HTML("Waiting for input...")
        self.drop_structure = ipw.Dropdown(description="",
                                           options=[("select structure", {
                                               "status": False
                                           })],
                                           style=style,
                                           layout=layout)
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


class OptimadeQueryWidget(ipw.VBox):
    """AiiDAlab-specific OPTIMADE Query widget

    Useful as a widget to integrate with the
    :class:`aiidalab_widgets_base.structures.StructureManagerWidget`,
    embedded into applications.

    NOTE: `embedded` for `OptimadeQueryFilterWidget` was introduced in `optimade-client`
    version 2020.11.5.

    :param embedded: Whether or not to show extra database and provider information.
        When set to `True`, the extra information will be hidden, this is useful
        in situations where the widget is used in a Tab or similar, e.g., for the
        :class:`aiidalab_widgets_base.structures.StructureManagerWidget`.
    :type embedded: bool
    :param title: Title used for Tab header if employed in
        :class:`aiidalab_widgets_base.structures.StructureManagerWidget`.
    :type title: str
    """

    structure = Instance(Atoms, allow_none=True)

    def __init__(
            self,
            embedded: bool = True,
            title: str = None,
            **kwargs,
    ) -> None:
        providers = OptimadeQueryProviderWidget(embedded=embedded)
        filters = OptimadeQueryFilterWidget(embedded=embedded)

        ipw.dlink((providers, 'database'), (filters, 'database'))

        filters.observe(self._update_structure, names='structure')

        self.title = title if title is not None else 'OPTIMADE'
        layout = kwargs.pop('layout') if 'layout' in kwargs else {'width': 'auto', 'height': 'auto'}

        super().__init__(
            children=(providers, filters),
            layout=layout,
            **kwargs,
        )

    def _update_structure(self, change: dict) -> None:
        """New structure chosen"""
        self.structure = change['new'].as_ase if change['new'] else None


class ComputerDatabaseWidget(ipw.HBox):
    """Extract the setup of a known computer from the AiiDA code registry."""
    # Verdi computer setup.
    label = Unicode()
    hostname = Unicode()
    description = Unicode()
    transport = Unicode()
    scheduler = Unicode()
    shebang = Unicode()
    work_dir = Unicode()
    mpirun_command = Unicode()
    mpiprocs_per_machine = Int()
    prepend_text = Unicode()
    append_text = Unicode()
    num_cores_per_mpiproc = Int()
    queue_name = Unicode()

    # Verdi computer configure.
    port = Int()
    allow_agent = Bool()
    safe_interval = Float()
    use_login_shell = Bool()
    proxy_hostname = Unicode()
    proxy_username = Unicode()
    proxy_command = Unicode()

    def __init__(self, **kwargs):
        self.database = {}
        self.update_btn = ipw.Button(description="Pull database")
        self.update_btn.on_click(self.update)
        self.domain = ipw.Dropdown(
            options=[],
            description='Domain',
            disabled=False,
        )
        self.domain.observe(self.update_computers, names=['value', 'options'])

        self.computer = ipw.Dropdown(
            options=[],
            description="Computer:",
            disable=False,
        )
        self.computer.observe(self.update_settings, names=['value', 'options'])

        super().__init__(children=[self.update_btn, self.domain, self.computer], **kwargs)

    def update(self, _=None):
        self.database = requests.get("https://aiidateam.github.io/aiida-code-registry/database.json").json()
        self.domain.options = self.database.keys()

    def update_computers(self, _=None):
        self.computer.options = [key for key in self.database[self.domain.value].keys() if key != "default"]
        self.computer.value = None  # This is a hack to make sure the selected computer appears as selected.
        self.computer.value = self.database[self.domain.value]["default"]

    def update_settings(self, _=None):
        """Read settings from the YAML files and populate self.database with them."""
        if self.domain.value is None or self.computer.value is None:
            return

        computer_settings = self.database[self.domain.value][self.computer.value]
        computer_setup = computer_settings['computer-setup']
        for setting in computer_setup:
            self.set_trait(setting, computer_setup[setting])
        if 'computer-configure' in computer_settings:
            computer_configure = computer_settings['computer-configure']
            for setting in computer_configure:
                self.set_trait(setting, computer_configure[setting])

    @validate('proxy_command')
    def _validate_proxy_command(self, change):
        """Extrac username and hostname for connecting to a proxy server."""
        command = change['value']
        username, hostname = ''.join([w for w in command.split() if '@' in w]).split('@')
        with self.hold_trait_notifications():
            self.proxy_username = username
            self.proxy_hostname = hostname


class CodeDatabaseWidget(ipw.HBox):
    """Extract the setup of a known computer from the AiiDA code registry."""
    label = Unicode()
    description = Unicode()
    input_plugin = Unicode()
    on_computer = Bool()
    remote_abs_path = Unicode()
    computer = Unicode()
    prepend_text = Unicode()
    append_text = Unicode()

    def __init__(self, **kwargs):
        self.database = {}

        # Select domain.
        self.inp_domain = ipw.Dropdown(
            options=[],
            description='Domain',
            disabled=False,
        )
        self.inp_domain.observe(self.update_computers, names=['value', 'options'])

        # Select computer.
        self.inp_computer = ipw.Dropdown(
            options=[],
            description="Computer:",
            disable=False,
        )
        self.inp_computer.observe(self.update_codes, names=['value', 'options'])

        # Select code.
        self.inp_code = ipw.Dropdown(
            options=[],
            description="Code:",
            disable=False,
        )
        self.inp_code.observe(self.update_settings, names=['value', 'options'])

        self.update_btn = ipw.Button(description="Pull database")
        self.update_btn.on_click(self.update)
        super().__init__(children=[self.update_btn, self.inp_domain, self.inp_computer, self.inp_code], **kwargs)

    def update(self, _=None):
        self.database = requests.get("https://aiidateam.github.io/aiida-code-registry/database.json").json()
        self.inp_domain.options = self.database.keys()

    def update_computers(self, _=None):
        self.inp_computer.options = [key for key in self.database[self.inp_domain.value].keys() if key != "default"]
        self.inp_computer.value = None  # This is a hack to make sure the selected computer appears as selected.
        self.inp_computer.value = self.database[self.inp_domain.value]["default"]

    def update_codes(self, _=None):
        """Read settings from the YAML files and populate self.database with them."""
        if self.inp_domain.value is None or self.inp_computer.value is None:
            return
        self.inp_code.options = [
            key for key in self.database[self.inp_domain.value][self.inp_computer.value].keys()
            if key not in ('computer-setup', 'computer-configure')
        ]

    def update_settings(self, _=None):
        """Update code settings."""
        if self.inp_domain.value is None or self.inp_computer.value is None or self.inp_code.value is None:
            return
        settings = self.database[self.inp_domain.value][self.inp_computer.value][self.inp_code.value]
        for key, value in settings.items():
            self.set_trait(key, value)
