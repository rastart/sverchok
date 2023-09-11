
import numpy as np

import bpy
from bpy.props import FloatProperty, EnumProperty, BoolProperty, IntProperty

from sverchok.node_tree import SverchCustomTreeNode
from sverchok.data_structure import updateNode, zip_long_repeat, ensure_nesting_level

from sverchok.utils.field.vector import SvVectorField
from sverchok.utils.curve import SvDeformedByFieldCurve, SvCurve
from sverchok.utils.curve.nurbs import SvNurbsCurve

class SvApplyFieldToCurveNode(SverchCustomTreeNode, bpy.types.Node):
        """
        Triggers: Apply field to curve
        Tooltip: Apply vector field to curve
        """
        bl_idname = 'SvExApplyFieldToCurveNode'
        bl_label = 'Apply Field to Curve'
        bl_icon = 'CURVE_NCURVE'
        bl_icon = 'OUTLINER_OB_EMPTY'
        sv_icon = 'SV_CURVE_VFIELD'

        coefficient : FloatProperty(
                name = "Coefficient",
                description = "Vector field application coefficient (0 means vector field will have no effect)",
                default = 1.0,
                update=updateNode)

        use_control_points : BoolProperty(
                name = "Use Control Points",
                description = "If checked, then the vector field will be applied to control points of a NURBS curve, instead of applying it to all points of the curve. This node will fail (become red) if this mode is enabled, but input curve is not a NURBS and can not be presented as a NURBS. If not checked, then the node will apply the vector fields to all points of the curve; in such a case, it can process any type of curve",
                default = False,
                update=updateNode)

        join : BoolProperty(
                name = "Join",
                description = "Output single flat list of curves",
                default = True,
                update=updateNode)

        def sv_init(self, context):
            self.inputs.new('SvVectorFieldSocket', "Field")
            self.inputs.new('SvCurveSocket', "Curve")
            self.inputs.new('SvStringsSocket', "Coefficient").prop_name = 'coefficient'
            self.outputs.new('SvCurveSocket', "Curve")

        def draw_buttons(self, context, layout):
            layout.prop(self, "use_control_points", toggle=False)
            layout.prop(self, "join", toggle=False)

        def process(self):
            if not any(socket.is_linked for socket in self.outputs):
                return

            curve_s = self.inputs['Curve'].sv_get()
            field_s = self.inputs['Field'].sv_get()
            coeff_s = self.inputs['Coefficient'].sv_get()

            curve_s = ensure_nesting_level(curve_s, 2, data_types=(SvCurve,))
            field_s = ensure_nesting_level(field_s, 2, data_types=(SvVectorField,))
            coeff_s = ensure_nesting_level(coeff_s, 2)

            curve_out = []
            for curve_i, field_i, coeff_i in zip_long_repeat(curve_s, field_s, coeff_s):
                new_curves = []
                for curve, field, coeff in zip_long_repeat(curve_i, field_i, coeff_i):
                    if self.use_control_points:
                        nurbs = SvNurbsCurve.to_nurbs(curve)
                        if nurbs is not None:
                            control_points = nurbs.get_control_points()
                        else:
                            raise Exception("Curve is not a NURBS!")

                        cpt_xs = control_points[:,0]
                        cpt_ys = control_points[:,1]
                        cpt_zs = control_points[:,2]

                        cpt_dxs, cpt_dys, cpt_dzs = field.evaluate_grid(cpt_xs, cpt_ys, cpt_zs)
                        xs = cpt_xs + coeff * cpt_dxs
                        ys = cpt_ys + coeff * cpt_dys
                        zs = cpt_zs + coeff * cpt_dzs

                        control_points = np.stack((xs, ys, zs)).T

                        knotvector = nurbs.get_knotvector()
                        #old_t_min, old_t_max = curve.get_u_bounds()
                        #knotvector = sv_knotvector.rescale(knotvector, old_t_min, old_t_max)
                        new_curve = SvNurbsCurve.build(nurbs.get_nurbs_implementation(),
                                        nurbs.get_degree(), knotvector, 
                                        control_points, nurbs.get_weights())
                        new_curve.u_bounds = nurbs.u_bounds
                    else:
                        new_curve = SvDeformedByFieldCurve(curve, field, coeff)
                    new_curves.append(new_curve)

                if self.join:
                    curve_out.extend(new_curves)
                else:
                    curve_out.append(new_curves)

            self.outputs['Curve'].sv_set(curve_out)

def register():
    bpy.utils.register_class(SvApplyFieldToCurveNode)

def unregister():
    bpy.utils.unregister_class(SvApplyFieldToCurveNode)

