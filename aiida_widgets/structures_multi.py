from __future__ import print_function

import os
import ase.io
import ipywidgets as ipw
from ipywidgets import Layout
from IPython.display import clear_output
from fileupload import FileUploadWidget
import tarfile
import zipfile
import tempfile
import nglview


class MultiStructureUploadWidget(ipw.VBox):
    def __init__(self, text="Upload Zip or Tar archive", node_class=None, **kwargs):
        """ Upload multiple structures and store them in AiiDA database.

        :param text: Text to display before upload button
        :type text: str
        :param node_class: AiiDA node class for storing the structure.
            Possible values: 'StructureData', 'CifData' or None (let the user decide).
            Note: If your workflows require a specific node class, better fix it here.
        """

        self.file_upload = FileUploadWidget(text)
        self.viewer = nglview.NGLWidget()
        self.selection_slider = ipw.SelectionSlider(
            options=[None,],
            disabled=False,
            orientation='vertical',
            description='Browse structures:',
            readout=False,
            layout = Layout(width='50%'),
        )
        
        view = ipw.HBox([self.viewer, self.selection_slider])
        
        self.selection_slider.on_trait_change(self.change_structure, 'value')
        self.btn_store_all = ipw.Button(description='Store all in AiiDA', disabled=True)
        self.btn_store_selected = ipw.Button(description='Store selected', disabled=True)
        self.structure_description = ipw.Text(placeholder="Description (optional)")
        self.structure_ase = None # contains the selected structure in the ase format
        self.structure_nodes = [] # a list that contains all stored structure objects
        self.structure_names = [] # list of uploaded structures
        self.data_format = ipw.RadioButtons(
            options=['StructureData', 'CifData'], description='Data type:')

        if node_class is None:
            store = ipw.HBox(
                [self.btn_store_all, self.data_format, self.structure_description, self.btn_store_selected])
        else:
            store = ipw.HBox([self.btn_store_all, self.structure_description, self.btn_store_selected])
            self.data_format.value = node_class
        children = [self.file_upload, view, store]

        super(MultiStructureUploadWidget, self).__init__(
            children=children, **kwargs)

        self.file_upload.observe(self._on_file_upload, names='data')
        self.btn_store_all.on_click(self._on_click_store_all)
        self.btn_store_selected.on_click(self._on_click_store_selected)

        from aiida import load_dbenv, is_dbenv_loaded
        from aiida.backends import settings
        if not is_dbenv_loaded():
            load_dbenv(profile=settings.AIIDADB_PROFILE)
    
    def change_structure(self):
        if self.selection_slider.value is None:
            pass
        else:
            self.select_structure(filepath=self.selection_slider.value)

    # pylint: disable=unused-argument
    def _on_file_upload(self, change):
        # I redefine both: structure_names and structure_nodes, since we are now uploading a different archive
        self.structure_names = []
        self.structure_nodes = []

        # download an archive and put its content into a file
        archive = tempfile.NamedTemporaryFile(suffix=self.file_upload.filename)
        with open(archive.name, 'w') as f:
            f.write(self.file_upload.data)
        self.archive_name = archive.name

        # create a temporary folder where all the structure will be extracted
        self.tmp_folder = tempfile.mkdtemp()

        # extract tar archive
        if tarfile.is_tarfile(self.archive_name):
            try:
                with tarfile.open(self.archive_name, "r:*", format=tarfile.PAX_FORMAT) as tar:
                    for member in tar.getmembers():
                        tar.extract(path=self.tmp_folder, member=member)
            except tarfile.ReadError:
                raise ValueError("The input tar file is corrupted.")

        # extract zip archive
        elif zipfile.is_zipfile(self.archive_name):
            print("Extracting zip")
            try:
                with zipfile.ZipFile(self.archive_name, "r", allowZip64=True) as zipf:
                    if not zipf.namelist():
                        raise ValueError("The zip file is empty.")
                    for member in zipf.namelist():
                        zipf.extract(path=self.tmp_folder, member=member)
            except zipfile.BadZipfile:
                raise ValueError("The input zip file is corrupted.")
        print("Extracted to {}".format(self.tmp_folder))
        for (dirpath, dirnames, filenames) in os.walk(self.tmp_folder):
            for filename in filenames:
                self.structure_names.append(dirpath+'/'+filename)

        # redefining the options for the slider and its default value
        # together with slider's value update the structure selection also changes,
        # as change_structure() called on slider's value change
        self.selection_slider.options = self.structure_names
        self.selection_slider.value = self.structure_names[0]

    def get_ase(self, filepath):
        try:
            traj = ase.io.read(filepath, index=":")
        except AttributeError:
            print("Looks like {} file does not contain structure coordinates".format(filepath))
            return None
        if len(traj) > 1:
            print("Warning: Uploaded file {} contained more than one structure. I take the first one.".format(filepath))
        return traj[0]

    def get_description(self, structure_ase, filepath):
        formula = structure_ase.get_chemical_formula()
        return "{} ({})".format(formula, filepath.split('/')[-1])

    def select_structure(self, filepath):
        structure_ase = self.get_ase(filepath)
        self.btn_store_all.disabled = False
        self.btn_store_selected.disabled = False

        if structure_ase is None:
            self.structure_ase = None
            self.btn_store_selected.disabled = True
            self.refresh_view()
            return

        self.structure_description.value = self.get_description(structure_ase, filepath)
        self.structure_ase = structure_ase
        self.refresh_view()


    def refresh_view(self):
        viewer = self.viewer
        # Note: viewer.clear() only removes the 1st component
        # pylint: disable=protected-access
        for comp_id in viewer._ngl_component_ids:
            viewer.remove_component(comp_id)
        if self.structure_ase is None:
            return
        viewer.add_component(nglview.ASEStructure(
            self.structure_ase))  # adds ball+stick
        viewer.add_unitcell()

    # pylint: disable=unused-argument
    def _on_click_store_all(self, change):
        self.structure_nodes = []
        self.selection_slider.disabled = True
        for filepath in self.structure_names:
            self.store_structure(filepath)
        self.selection_slider.disabled = False

    # pylint: disable=unused-argument
    def _on_click_store_selected(self, change):
        self.store_structure(self.selection_slider.value, description=self.structure_description.value)

    def store_structure(self, filepath, description=None):
        structure_ase = self.get_ase(filepath)
        if structure_ase is None:
            return

        # determine data source
        if filepath.endswith('.cif'):
            source_format = 'CIF'
        else:
            source_format = 'ASE'

        # perform conversion
        if self.data_format.value == 'CifData':
            if source_format == 'CIF':
                from aiida.orm.data.cif import CifData
                structure_node = CifData(
                    file=filepath,
                    scan_type='flex',
                    parse_policy='lazy')
            else:
                from aiida.orm.data.cif import CifData
                structure_node = CifData()
                structure_node.set_ase(structure_ase)
        else:
            # Target format is StructureData
            from aiida.orm.data.structure import StructureData
            structure_node = StructureData(ase=structure_ase)

            #TODO: Figure out whether this is still necessary for StructureData
            # ensure that tags got correctly translated into kinds
            for t1, k in zip(structure_ase.get_tags(),
                             structure_node.get_site_kindnames()):
                t2 = int(k[-1]) if k[-1].isnumeric() else 0
                assert t1 == t2
        if description is None:
            structure_node.description = self.get_description(structure_ase, filepath)
        else:
            structure_node.description = description
        structure_node.label = ".".join(filepath.split('/')[-1].split('.')[:-1])
        structure_node.store()
        self.structure_nodes.append(structure_node)
        print("Stored in AiiDA: " + repr(structure_node))

    @property
    def node_class(self):
        return self.data_format.value

    @node_class.setter
    def node_class(self, value):
        self.data_format.value = value