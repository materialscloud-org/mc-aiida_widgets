import io
import ipywidgets as ipw
import traitlets
from aiida.plugins import DataFactory
from aiida.orm import Node, QueryBuilder
from IPython.display import clear_output, display

from traitlets import observe
from aiidalab_eln.uploader import object_uploader

import tempfile
import json
from pathlib import Path


TOKEN_FILE_PATH = Path(tempfile.gettempdir()) / "aiidalab-eln-tokens.json"


def get_token(token_type, uuid):
    token_file = TOKEN_FILE_PATH
    try:
        with open(token_file, "r") as file:
            tokens = json.load(file)
            return tokens[token_type][uuid]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def update_token(token_type, uuid, token):
    token_file = TOKEN_FILE_PATH
    try:
        with open(token_file, "r") as file:
            tokens = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        tokens = {}

    if token_type not in tokens:
        tokens[token_type] = {}
    tokens[token_type][uuid] = token

    with open(token_file, "w") as file:
        json.dump(tokens, file, indent=4)


class AppIcon:
    def __init__(self, icon, link, description):
        self.icon = icon
        self.link = link
        self.description = description

    def to_html_string(self):
        return f"""
            <table style="border-collapse:separate;border-spacing:15px;">
            <tr>
                <td style="width:200px"> <a href="{self.link}" target="_blank">  <img src="{self.icon}"> </a></td>
                <td style="width:800px"> <p style="font-size:16px;">{self.description} </p></td>
            </tr>
            </table>
            """


class DisplayAiidaObject(ipw.VBox):
    node = traitlets.Instance(Node, allow_none=True)

    def __init__(self, **kwargs):
        self._output = ipw.Output()
        super().__init__(
            children=[
                self._output,
            ],
            **kwargs,
        )

    @traitlets.observe("node")
    def _observe_node(self, change):
        from aiidalab_widgets_base import viewer

        if change["new"] != change["old"]:
            with self._output:
                clear_output()
                if change["new"]:
                    display(viewer(change["new"]))


class ElnImportWidget(ipw.VBox):

    node = traitlets.Instance(Node, allow_none=True)

    def __init__(self, **kwargs):
        from cheminfopy import Sample

        eln_instance = kwargs["eln_instance"] if "eln_instance" in kwargs else None
        sample_uuid = kwargs["sample_uuid"] if "sample_uuid" in kwargs else None
        spectrum_type = kwargs["spectrum_type"] if "spectrum_type" in kwargs else None
        file_name = kwargs["file_name"] if "file_name" in kwargs else None

        if "sample_token" in kwargs:
            sample_token = kwargs["sample_token"]
            update_token("sample", sample_uuid, sample_token)
        else:
            sample_token = get_token("sample", sample_uuid)

        # Importing the object:
        if eln_instance and sample_uuid and sample_token:
            object_type = DataFactory("cif")
            sample = Sample(
                instance=eln_instance, sample_uuid=sample_uuid, token=sample_token
            )
            content = sample.get_spectrum(spectrum_type=spectrum_type, name=file_name)
            file = io.BytesIO(bytes(content, "utf8"))
            self.node = object_type(file=file)

            eln_info = {
                "eln_instance": eln_instance,
                "sample_uuid": sample_uuid,
                "spectrum_type": spectrum_type,
                "file_name": file_name,
            }
            self.node.set_extra("eln", eln_info)
            self.node.store()
        else:
            self.node = None


class OpenInApp(ipw.VBox):

    node = traitlets.Instance(Node, allow_none=True)

    def __init__(self, **kwargs):
        self.tab = ipw.Tab()
        self.tab_selection = ipw.RadioButtons(
            options=[],
            description="",
            disabled=False,
            style={"description_width": "initial"},
            layout=ipw.Layout(width="auto"),
        )
        spacer = ipw.HTML("""<p style="margin-bottom:1cm;"></p>""")
        super().__init__(children=[self.tab_selection, spacer, self.tab], **kwargs)

    @traitlets.observe("node")
    def _observe_node(self, change):
        if change["new"]:
            self.tab.children = [
                self.get_geo_opt_tab(),
                self.get_geometry_analysis_tab(),
                self.get_isotherm_tab(),
            ]
            self.tab.set_title(0, "Geometry Optimization")
            self.tab.set_title(1, "Geometry analysis")
            self.tab.set_title(2, "Isotherm")

            self.tab_selection.options = [
                (
                    "Geometry Optimization - typically this is the first step needed to find optimal positions of atoms in the unit cell.",
                    0,
                ),
                (
                    "Geometry analysis - calculate parameters describing the geometry of a porous material.",
                    1,
                ),
                (
                    "Isotherm - compute adsorption isotherm of a small molecules in the selected material. ",
                    2,
                ),
            ]
            ipw.link((self.tab, "selected_index"), (self.tab_selection, "value"))
        else:
            self.tab.children = []

    def get_geo_opt_tab(self):
        geo_opt = ipw.HTML("")

        geo_opt.value += AppIcon(
            icon="https://gitlab.com/QEF/q-e/raw/develop/logo.jpg",
            link=f"https://aiidalab-demo.materialscloud.org/user-redirect/apps/apps/quantum-espresso/qe.ipynb?structure_uuid={self.node.uuid}",
            description="Optimize atomic positions and/or unit cell employing Quantum ESPRESSO. Quantum ESPRESSO is preferable for small structures with no cell dimensions larger than 15 Å. Additionally, you can choose to compute electronic properties of the material such as band structure and density of states.",
        ).to_html_string()

        geo_opt.value += AppIcon(
            icon="https://raw.githubusercontent.com/lsmo-epfl/aiidalab-epfl-lsmo/develop/miscellaneous/logos/LSMO.png",
            link=f"https://aiidalab-demo.materialscloud.org/user-redirect/apps/apps/aiidalab-lsmo/multistage_geo_opt_ddec.ipynb?structure_uuid={self.node.uuid}",
            description="Optimize atomic positions and unit cell with CP2K. CP2K is very efficient for large and/or porous structures. A structure is considered large when any cell dimension is larger than 15 Å. Additionally, you can choose to assign point charges to the atoms using DDEC.",
        ).to_html_string()

        return geo_opt

    def get_isotherm_tab(self):
        isotherm = ipw.HTML()
        isotherm.value += AppIcon(
            icon="https://raw.githubusercontent.com/lsmo-epfl/aiidalab-epfl-lsmo/develop/miscellaneous/logos/LSMO.png",
            link=f"https://aiidalab-demo.materialscloud.org/user-redirect/apps/apps/aiidalab-lsmo/compute_isotherm.ipynb?structure_uuid={self.node.uuid}",
            description="Compute adsorption isotherm of the selected material using the RASPA code. Typically, one needs to optimize geometry and compute the charges of material before isotherm. However, if this is already done, you can go for it.",
        ).to_html_string()

        return isotherm

    def get_geometry_analysis_tab(self):
        geo_analysis = ipw.HTML()
        geo_analysis.value += AppIcon(
            icon="https://raw.githubusercontent.com/lsmo-epfl/aiidalab-epfl-lsmo/develop/miscellaneous/logos/LSMO.png",
            link=f"https://aiidalab-demo.materialscloud.org/user-redirect/apps/apps/aiidalab-lsmo/pore_analysis.ipynb?structure_uuid={self.node.uuid}",
            description="Perform geometry analysis of a material employing Zeo++ code.",
        ).to_html_string()

        return geo_analysis


class ElnExportWidget(ipw.VBox):
    node = traitlets.Instance(Node, allow_none=True)

    def __init__(self, **kwargs):
        self.eln_instance = ipw.Text(
            description="ELN:",
            value="",
            style={"description_width": "initial"},
        )
        self.sample_uuid = ipw.Text(
            description="Sample ID:",
            value="",
            style={"description_width": "initial"},
        )
        self.file_name = ipw.Text(
            description="File name:",
            value="",
            style={"description_width": "initial"},
        )
        self.token = ipw.Text(
            description="Token:",
            value="",
            style={"description_width": "initial"},
        )

        self.send = ipw.Button(description="Send to ELN")
        self.send.on_click(self.send_to_eln)
        self.modify_settings = ipw.Checkbox(
            description="Modify ELN settings.", indent=False
        )
        self.modify_settings.observe(self.handle_output, "value")
        self._output = ipw.Output()
        children = [
            ipw.HBox([self.send, self.modify_settings]),
            self._output,
        ]
        super().__init__(children=children, **kwargs)

    @observe("node")
    def _observe_node(self, _=None):
        if self.node is None:
            return

        if "eln" in self.node.extras:
            info = self.node.extras["eln"]
        else:
            try:
                q = QueryBuilder().append(
                    Node,
                    filters={"extras": {"has_key": "eln"}},
                    tag="source_node",
                    project="extras.eln",
                )
                q.append(
                    Node, filters={"uuid": self.node.uuid}, with_ancestors="source_node"
                )
                info = q.all(flat=True)[0]
            except IndexError:
                info = {}

        self.eln_instance.value = info["eln_instance"] if "eln_instance" in info else ""
        self.sample_uuid.value = info["sample_uuid"] if "sample_uuid" in info else ""
        self.file_name.value = self.node.uuid
        if "sample_uuid" in info:
            self.token.value = get_token("sample", info["sample_uuid"]) or ""
        else:
            self.token.value = ""

    def send_to_eln(self, _=None):

        if (
            not self.eln_instance.value
            or not self.sample_uuid.value
            or not self.token.value
            or not self.file_name.value
        ):
            self.modify_settings.value = True
            with self._output:
                print("Please provide the missing parameters!")
            return

        object_uploader(
            self.node,
            eln_instance=self.eln_instance.value,
            sample_uuid=self.sample_uuid.value,
            token=self.token.value,
            filename=self.file_name.value,
        )

    def handle_output(self, _=None):
        with self._output:
            clear_output()
            if self.modify_settings.value:
                display(
                    ipw.VBox(
                        [
                            self.eln_instance,
                            self.sample_uuid,
                            self.file_name,
                            self.token,
                        ]
                    )
                )
