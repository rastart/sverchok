import bpy
from bpy.props import StringProperty, BoolProperty,EnumProperty

from sverchok.node_tree import SverchCustomTreeNode # OLD throttled
from sverchok.data_structure import updateNode, match_long_repeat # NEW throttle_and_update_node
from sverchok.utils.sv_logging import sv_logger
from sverchok.dependencies import FreeCAD
from sverchok.utils.sv_operator_mixins import SvGenericNodeLocator

if FreeCAD is not None:
    F = FreeCAD


class SvWriteFCStdOperator(bpy.types.Operator, SvGenericNodeLocator):

    bl_idname = "node.sv_write_fcstd_operator"
    bl_label = "write freecad file"
    bl_options = {'INTERNAL', 'REGISTER'}

    def execute(self, context):
        node = self.get_node(context)

        if not node: return {'CANCELLED'}

        node.write_FCStd(node)
        updateNode(node,context)

        return {'FINISHED'}


class SvWriteFCStdOperator(bpy.types.Operator, SvGenericNodeLocator):

    bl_idname = "node.sv_write_fcstd_operator"
    bl_label = "write freecad file"
    bl_options = {'INTERNAL', 'REGISTER'}

    def execute(self, context):
        node = self.get_node(context)

        if not node: return {'CANCELLED'}     

        node.write_FCStd(node)
        updateNode(node,context)

        return {'FINISHED'}


class SvWriteFCStdNode(SverchCustomTreeNode, bpy.types.Node):
    """
    Triggers: write FreeCAD file
    Tooltip: write parts in a .FCStd file 
    """

    bl_idname = 'SvWriteFCStdNode'
    bl_label = 'Write FCStd'
    bl_icon = 'IMPORT'
    solid_catergory = "Inputs"
    
    write_update : BoolProperty(
        name="write_update", 
        default=False)

    part_name : StringProperty(
        name="part_name", 
        default="part_name")

    #@throttled
    def changeMode(self, context):

        if self.obj_format == 'mesh' or self.obj_format == 'wire':
            if 'Verts' not in self.inputs:
                self.inputs.remove(self.inputs['Solid'])
                self.inputs.new('SvVerticesSocket', 'Verts')
                self.inputs.new('SvStringsSocket', 'Edges')
                self.inputs.new('SvStringsSocket', 'Faces')
                return
                
        else:
            if 'Solid' not in self.inputs:
                self.inputs.remove(self.inputs['Verts'])
                self.inputs.remove(self.inputs['Faces'])
                self.inputs.remove(self.inputs['Edges'])
                self.inputs.new('SvSolidSocket', 'Solid')
                return

    
    obj_format : EnumProperty(
                name='format',
                description='choose format',
                items={
                ('solid', 'solid', 'solid'),
                ('wire', 'wire', 'wire'),
                ('mesh', 'mesh', 'mesh')},
                default='solid',
                update=changeMode)

    def draw_buttons(self, context, layout):

        layout.label(text="write name:")
        col = layout.column(align=True)
        col.prop(self, 'part_name',text="")  
        col.prop(self, 'obj_format',text="")     
        col.prop(self, 'write_update')
        if self.obj_format == 'mesh':
            col.label(text="need triangle meshes")
        self.wrapper_tracked_ui_draw_op(layout, SvWriteFCStdOperator.bl_idname, icon='FILE_REFRESH', text="UPDATE")  


    def sv_init(self, context):
        self.inputs.new('SvFilePathSocket', "File Path")

        if self.obj_format == 'mesh' or self.obj_format == 'wire':
            self.inputs.new('SvVerticesSocket', "Verts")
            self.inputs.new('SvStringsSocket', "Faces")
            self.inputs.new('SvStringsSocket', "Edges")

        else:
            self.inputs.new('SvSolidSocket', 'Solid')
        
    def write_FCStd(self,node):

        if not node.inputs['File Path'].is_linked:
            return
        
        files = node.inputs['File Path'].sv_get()

        if  not len(files[0]) == 1:
            print ('FCStd write node support just 1 file at once')
            return

        fc_file=files[0][0]

        if node.obj_format == 'mesh' or self.obj_format == 'wire':

            if any((node.inputs['Verts'].is_linked, node.inputs['Faces'].is_linked)):

                verts_in = node.inputs['Verts'].sv_get(deepcopy=False)
                pols_in = node.inputs['Faces'].sv_get(deepcopy=False)
                edge_in = node.inputs['Edges'].sv_get(deepcopy=False)
                verts, pols, edges = match_long_repeat([verts_in, pols_in,edge_in])
                fc_write_parts(fc_file, verts, pols, edges, node.part_name, None, node.obj_format)

        elif node.obj_format == 'solid':

            if node.inputs['Solid'].is_linked:
                solid=node.inputs['Solid'].sv_get()
                fc_write_parts(fc_file, None, None, None, node.part_name, solid, node.obj_format)

        else:
            return

    def process(self):

        if self.write_update:
            self.write_FCStd(self)   
        else:
            return



def fc_write_parts(fc_file, verts, faces, edges, part_name, solid, mod):

    try:
        from os.path import exists

        Fname = bpy.path.display_name_from_filepath(fc_file)

        if not exists(fc_file):
            doc = F.newDocument(Fname)
            doc.recompute()
            doc.saveAs(fc_file) # using full filepath, saveAs also sets doc.FileName internally

        F.open(fc_file)

    except Exception as err:
        info(f'FCStd open error, {err}')
        return

    F.setActiveDocument(Fname)
    fc_root = F.getDocument(Fname)

    obj_names = set( [ i.Name for i in fc_root.Objects] )

    part_name += '_sv_' #->suffix added to avoid deleting freecad objects erroneously

    # SEARCH the freecad project for previous writed parts from this node

    if part_name in obj_names: #if the part name is numberless is detected as single
        fc_root.removeObject(part_name)

    else:
        for name in obj_names: #if not, check the fc project if there are parts with same root name
            if part_name in name:
                fc_root.removeObject(name)

    ############### if there, previous writed parts are removed ####################
    ############### so then write them again...

    if mod == 'solid': #EXPORT SOLID 

        for i, s in enumerate(solid):      
            new_part = F.ActiveDocument.addObject( "Part::Feature",part_name+str(i) ) #multiple: give numbered name
            new_part.Shape = s

    elif mod == 'wire':
        #faces -> ([vindex])
        #verts -> (x,y,z)
        #import Draft
        import Part
        for i,f in  enumerate(faces[0]):
            #f-> [v,v,v,v,v]
            edge_group = []
            for e in edges[0]:
                if e[0] in f and e[1] in f:
                    v1= verts[0][e[0]]
                    v2= verts[0][e[1]]
                    start, end = FreeCAD.Vector(v1[0],v1[1],v1[2]), FreeCAD.Vector(v2[0],v2[1],v2[2])
                    line=Part.makeLine(start, end)
                    edge_group.append(line)
                    print(line)
                    
            wire = Part.Wire( Part.__sortEdges__(edge_group) )
            Part.show(wire,part_name+str(i))
                    
    else: #EXPORT MESH
        
        import Mesh
        
        for i in range(len(verts)):

            temp_faces = faces[i]
            temp_verts = verts[i]
            meshdata = []

            for f in temp_faces:
                v1,v2,v3 = f[0],f[1],f[2]
                meshdata.append( temp_verts[v1] )
                meshdata.append( temp_verts[v2] )
                meshdata.append( temp_verts[v3] )

            mesh = Mesh.Mesh( meshdata )
            obj = F.ActiveDocument.addObject( "Mesh::Feature", part_name+str(i) )
            obj.Mesh = mesh
    
    

    F.ActiveDocument.recompute()
    F.getDocument(Fname).save()
    F.closeDocument(Fname)


def register():
    bpy.utils.register_class(SvWriteFCStdNode)
    bpy.utils.register_class(SvWriteFCStdOperator)


def unregister():
    bpy.utils.unregister_class(SvWriteFCStdNode)
    bpy.utils.unregister_class(SvWriteFCStdOperator)
