'''
Created on Aug 15, 2017
@author: Patrick

This module contains functions that are used to mark and set
landmarks on the casts.  For example marking splint boundaries
midine etc.
'''
import bpy
import bmesh
import odcutils
from points_picker import PointPicker
from textbox import TextBox
from mathutils import Vector, Matrix, Color
from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_origin_3d, region_2d_to_vector_3d
import math
from mesh_cut import flood_selection_faces, edge_loops_from_bmedges, flood_selection_faces_limit, space_evenly_on_path
from curve import CurveDataManager, PolyLineKnife
from common_utilities import bversion
import tracking

def arch_crv_draw_callback(self, context):  
    self.crv.draw(context)
    self.help_box.draw()   
    
class D3SPLINT_OT_splint_occlusal_arch_max(bpy.types.Operator):
    """Draw a line along the cusps of the maxillary model"""
    bl_idname = "d3splint.draw_occlusal_curve_max"
    bl_label = "Mark Occlusal Curve"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls,context):
        return True

            
    def modal_nav(self, event):
        events_nav = {'MIDDLEMOUSE', 'WHEELINMOUSE','WHEELOUTMOUSE', 'WHEELUPMOUSE','WHEELDOWNMOUSE'} #TODO, better navigation, another tutorial
        handle_nav = False
        handle_nav |= event.type in events_nav

        if handle_nav: 
            return 'nav'
        return ''
    
    
    def  convert_curve_to_plane(self, context):
        
        me = self.crv.crv_obj.to_mesh(context.scene, apply_modifiers = True, settings = 'PREVIEW')
        mx = self.crv.crv_obj.matrix_world
        arch_vs = [mx*v.co for v in me.vertices]
        arc_vs_even, eds = space_evenly_on_path(arch_vs, [(0,1),(1,2)], 101, 0)
        
        v_ant = arc_vs_even[50] #we established 100 verts so 50 is the anterior midpoint
        v_0 = arc_vs_even[0]
        v_n = arc_vs_even[-1]
        
        center = .5 *(.5*(v_0 + v_n) + v_ant)
        
        vec_n = v_n - v_0
        vec_n.normalize()
        
        vec_ant = v_ant - v_0
        vec_ant.normalize()
        
        Z = vec_n.cross(vec_ant)
        Z.normalize()
        X = v_ant - center
        X.normalize()
        
        if Z.dot(Vector((0,0,1))) < 0:
            Z = -1 * Z
                
        Y = Z.cross(X)
        
        R = Matrix.Identity(3)  #make the columns of matrix U, V, W
        R[0][0], R[0][1], R[0][2]  = X[0] ,Y[0],  Z[0]
        R[1][0], R[1][1], R[1][2]  = X[1], Y[1],  Z[1]
        R[2][0] ,R[2][1], R[2][2]  = X[2], Y[2],  Z[2]
        
        R = R.to_4x4()
        T = Matrix.Translation(center + 4 * Z)
        T2 = Matrix.Translation(center + 10 * Z)
        
        bme = bmesh.new()
        bme.verts.ensure_lookup_table()
        bme.edges.ensure_lookup_table()
        bme.faces.ensure_lookup_table()
        bmesh.ops.create_grid(bme, x_segments = 200, y_segments = 200, size = 39.9)
        
        bme.to_mesh(me)
        plane_obj = bpy.data.objects.new('Occlusal Plane', me)
        plane_obj.matrix_world = T * R
        
        mat = bpy.data.materials.get("Plane Material")
        if mat is None:
            # create material
            mat = bpy.data.materials.new(name="Plane Material")
            mat.diffuse_color = Color((0.8, 1, .9))
        
        plane_obj.data.materials.append(mat)
        
        Opposing = bpy.data.objects.get(self.splint.get_mandible())
        cons = plane_obj.constraints.new('CHILD_OF')
        cons.target = Opposing
        cons.inverse_matrix = Opposing.matrix_world.inverted()
        
        context.scene.objects.link(plane_obj)
        plane_obj.hide = True
        bme.free()
        
        
        
        
        
            
    def modal_main(self,context,event):
        # general navigation
        nmode = self.modal_nav(event)
        if nmode != '':
            return nmode  #stop here and tell parent modal to 'PASS_THROUGH'

        #after navigation filter, these are relevant events in this state
        if event.type == 'G' and event.value == 'PRESS':
            if self.crv.grab_initiate():
                return 'grab'
            else:
                #error, need to select a point
                return 'main'
        
        if event.type == 'MOUSEMOVE':
            self.crv.hover(context, event.mouse_region_x, event.mouse_region_y)    
            return 'main'
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            x, y = event.mouse_region_x, event.mouse_region_y
            self.crv.click_add_point(context, x,y)
            return 'main'
        
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            self.crv.click_delete_point(mode = 'mouse')
            return 'main'
        
        if event.type == 'X' and event.value == 'PRESS':
            self.crv.delete_selected(mode = 'selected')
            return 'main'
            
        if event.type == 'RET' and event.value == 'PRESS':
            if self.splint.jaw_type == 'MANDIBLE':
                self.convert_curve_to_plane(context)
            self.splint.curve_max = True
            return 'finish'
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            return 'cancel' 

        return 'main'
    
    def modal_grab(self,context,event):
        # no navigation in grab mode
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            #confirm location
            self.crv.grab_confirm()
            return 'main'
        
        elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            #put it back!
            self.crv.grab_cancel()
            return 'main'
        
        elif event.type == 'MOUSEMOVE':
            #update the b_pt location
            self.crv.grab_mouse_move(context,event.mouse_region_x, event.mouse_region_y)
            return 'grab'
        
    def modal(self, context, event):
        context.area.tag_redraw()
        
        FSM = {}    
        FSM['main']    = self.modal_main
        FSM['grab']    = self.modal_grab
        FSM['nav']     = self.modal_nav
        
        nmode = FSM[self.mode](context, event)
        
        if nmode == 'nav': 
            return {'PASS_THROUGH'}
        
        if nmode in {'finish','cancel'}:
            context.space_data.show_manipulator = True
            context.space_data.transform_manipulators = {'TRANSLATE'}
            #clean up callbacks
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}
        
        if nmode: self.mode = nmode
        
        return {'RUNNING_MODAL'}

    def invoke(self,context, event):
        if len(context.scene.odc_splints) == 0:
            self.report({'ERROR'},'need to start splint')
            return {'CANCELLED'}
        
        n = context.scene.odc_splint_index
        self.splint = context.scene.odc_splints[n]
        self.crv = None
        margin = "Occlusal Curve Max"
        
        model = self.splint.get_maxilla()   
        if model != '' and model in bpy.data.objects:
            Model = bpy.data.objects[model]
            for ob in bpy.data.objects:
                ob.select = False
                ob.hide = True
            Model.select = True
            Model.hide = False
            context.scene.objects.active = Model
            bpy.ops.view3d.viewnumpad(type = 'BOTTOM')
            bpy.ops.view3d.view_selected()
            self.crv = CurveDataManager(context,snap_type ='OBJECT', 
                                        snap_object = Model, 
                                        shrink_mod = False, 
                                        name = margin,
                                        cyclic = 'FALSE')
            self.crv.crv_obj.parent = Model
            context.space_data.show_manipulator = False
            context.space_data.transform_manipulators = {'TRANSLATE'}
        else:
            self.report({'ERROR'}, "Need to set the Master Model first!")
            return {'CANCELLED'}
            
        
        #self.splint.occl = self.crv.crv_obj.name
        
        #TODO, tweak the modifier as needed
        help_txt = "DRAW MAXIILARY OCCLUSAL POINTS\n\nLeft Click on BUCCAL CUSPS and incisal edges \n Points will snap to objects under mouse \n Right click to delete a point n\ G to grab  \n ENTER to confirm \n ESC to cancel"
        self.help_box = TextBox(context,500,500,300,200,10,20,help_txt)
        self.help_box.snap_to_corner(context, corner = [1,1])
        self.mode = 'main'
        self._handle = bpy.types.SpaceView3D.draw_handler_add(arch_crv_draw_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self) 
        
        tracking.trackUsage("D3Splint:MaxBuccalCusps",None)

        return {'RUNNING_MODAL'}

def landmarks_draw_callback(self, context):  
    self.crv.draw(context)
    self.help_box.draw()    
    
class D3SPLINT_OT_splint_land_marks(bpy.types.Operator):
    """Define Right Molar, Left Molar, Midline"""
    bl_idname = "d3splint.splint_mark_landmarks"
    bl_label = "Define Model Landmarks"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls,context):
        return True
    
    def modal_nav(self, event):
        events_nav = {'MIDDLEMOUSE', 'WHEELINMOUSE','WHEELOUTMOUSE', 'WHEELUPMOUSE','WHEELDOWNMOUSE'} #TODO, better navigation, another tutorial
        handle_nav = False
        handle_nav |= event.type in events_nav

        if handle_nav: 
            return 'nav'
        return ''
    
    def modal_main(self,context,event):
        # general navigation
        nmode = self.modal_nav(event)
        if nmode != '':
            return nmode  #stop here and tell parent modal to 'PASS_THROUGH'

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if len(self.crv.b_pts) >= 3: return 'main' #can't add more
            
            x, y = event.mouse_region_x, event.mouse_region_y
            
            if len(self.crv.b_pts) == 0:
                txt = "Right Molar"
                help_txt = "DRAW LANDMARK POINTS\n Click on Symmetric Patient Left Side Molar Occlusal Surface"
                self.help_box.raw_text = help_txt
                self.help_box.format_and_wrap_text()
                
            elif len(self.crv.b_pts) == 1:
                txt = "Left Molar"
                help_txt = "DRAW LANDMARK POINTS\n Left Click Midline near Incisal Edge"
                self.help_box.raw_text = help_txt
                self.help_box.format_and_wrap_text()
                    
            else:
                txt = "Incisal Midline"
                help_txt = "DRAW LANDMARK POINTS\n Press Enter to Finish"
                self.help_box.raw_text = help_txt
                self.help_box.format_and_wrap_text()
                
            self.crv.click_add_point(context, x,y, label = txt)
            
            return 'main'
        
        if event.type == 'DEL' and event.value == 'PRESS':
            self.crv.click_delete_point()
            return 'main'
            
        if event.type == 'RET' and event.value == 'PRESS':
            if len(self.crv.b_pts) != 3:
                return 'main'
            self.finish(context)
            return 'finish'
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            return 'cancel' 

        return 'main'
    
        
    def modal(self, context, event):
        context.area.tag_redraw()
        
        FSM = {}    
        FSM['main']    = self.modal_main
        FSM['nav']     = self.modal_nav
        
        nmode = FSM[self.mode](context, event)
        
        if nmode == 'nav': 
            return {'PASS_THROUGH'}
        
        if nmode in {'finish','cancel'}:
            context.space_data.show_manipulator = True
            
            if nmode == 'finish':
                context.space_data.transform_manipulators = {'TRANSLATE', 'ROTATE'}
            else:
                context.space_data.transform_manipulators = {'TRANSLATE'}
            #clean up callbacks
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}
        
        if nmode: self.mode = nmode
        
        return {'RUNNING_MODAL'}

    def invoke(self,context, event):
        n = context.scene.odc_splint_index
        self.splint = context.scene.odc_splints[n]    
        
        model = self.splint.get_maxilla()
           
        if model != '' and model in bpy.data.objects:
            Model = bpy.data.objects[model]
            for ob in bpy.data.objects:
                ob.select = False
                ob.hide = True
            Model.select = True
            Model.hide = False
            context.scene.objects.active = Model
            
            bpy.ops.view3d.viewnumpad(type = 'FRONT')
            
            bpy.ops.view3d.view_selected()
            self.crv = PointPicker(context,snap_type ='OBJECT', snap_object = Model)
            context.space_data.show_manipulator = False
            context.space_data.transform_manipulators = {'TRANSLATE'}
            
        else:
            self.report({'ERROR'}, "Need to mark the UpperJaw model first!")
            return {'CANCELLED'}
        
        #TODO, tweak the modifier as needed
        help_txt = "DRAW LANDMARK POINTS\n Click on the Patient's Right Molar Occlusal Surface"
        self.help_box = TextBox(context,500,500,300,200,10,20,help_txt)
        self.help_box.snap_to_corner(context, corner = [1,1])
        self.mode = 'main'
        self._handle = bpy.types.SpaceView3D.draw_handler_add(landmarks_draw_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self) 
        return {'RUNNING_MODAL'}

    def finish(self, context):

        v_ant = self.crv.b_pts[2] #midline
        v_R = self.crv.b_pts[0] #R molar
        v_L = self.crv.b_pts[1] #L molar
        
        center = .5 *(.5*(v_R + v_L) + v_ant)
        
        #vector pointing from left to right
        vec_R = v_R - v_L
        vec_R.normalize()
        
        #vector pointing straight anterior
        vec_ant = v_ant - center
        vec_ant.normalize()
        
        Z = vec_R.cross(vec_ant)
        X = v_ant - center
        X.normalize()
                
        Y = Z.cross(X)
        
        R = Matrix.Identity(3)  #make the columns of matrix U, V, W
        R[0][0], R[0][1], R[0][2]  = X[0] ,Y[0],  Z[0]
        R[1][0], R[1][1], R[1][2]  = X[1], Y[1],  Z[1]
        R[2][0] ,R[2][1], R[2][2]  = X[2], Y[2],  Z[2]
        
        R = R.to_4x4()

        T = Matrix.Translation(center)
        
        #Lets Calculate the matrix transform for an
        #8 degree Fox plane cant.
        Z_w = Vector((0,0,1))
        X_w = Vector((1,0,0))
        Y_w = Vector((0,1,0))
        Fox_R = Matrix.Rotation(8 * math.pi /180, 3, 'Y')
        Z_fox = Fox_R * Z_w
        X_fox = Fox_R * X_w
        
        R_fox = Matrix.Identity(3)  #make the columns of matrix U, V, W
        R_fox[0][0], R_fox[0][1], R_fox[0][2]  = X_fox[0] ,Y_w[0],  Z_fox[0]
        R_fox[1][0], R_fox[1][1], R_fox[1][2]  = X_fox[1], Y_w[1],  Z_fox[1]
        R_fox[2][0] ,R_fox[2][1], R_fox[2][2]  = X_fox[2], Y_w[2],  Z_fox[2]

        
        Model =  bpy.data.objects[self.splint.get_maxilla()]
     
        mx_final = T * R
        mx_inv = mx_final.inverted()
        
        #average distance from campers plane to occlusal
        #plane is 30 mm
        #file:///C:/Users/Patrick/Downloads/CGBCC4_2014_v6n6_483.pdf
        incisal_final = Vector((90, 0, -30))
        
        T2 = Matrix.Translation(incisal_final - mx_inv * v_ant)
        mx_mount = T2 * R_fox.to_4x4()
        
        Model.data.transform(mx_inv)
        #Model.matrix_world = Matrix.Identity(4)
        Model.matrix_world = mx_mount
        
        Opposing = bpy.data.objects.get(self.splint.get_mandible())
        if Opposing:
            Opposing.data.transform(mx_inv)
            #Opposing.matrix_world = Matrix.Identity(4)
            Opposing.matrix_world = mx_mount
            Opposing.hide = False
        
            #todo..check to move lower jaw after landmarks?    
            if len(Opposing.constraints):
                for cons in Opposing.constraints:
                    Opposing.constraints.remove(cons)
                    
            cons = Opposing.constraints.new('CHILD_OF')
            cons.target = Model
            cons.inverse_matrix = Model.matrix_world.inverted()
        
        if "Trim Surface" in bpy.data.objects:
            trim_ob = bpy.data.objects['Trim Surface']
            trim_ob.data.transform(mx_inv)
            trim_ob.matrix_world = mx_mount
            trim_ob.hide = True
        
        buccal = self.splint.name + '_buccal'
        if buccal in bpy.data.objects:
            bobj = bpy.data.objects[buccal]
            bobj.data.transform(mx_inv)
            bobj.matrix_world = mx_mount
            bobj.hide = True
        if "Trimmed_Model" in bpy.data.objects:
            trim_ob = bpy.data.objects["Trimmed_Model"]
            trim_ob.data.transform(mx_inv)
            trim_ob.matrix_word = mx_mount
            trim_ob.hide = True
        
        context.scene.cursor_location = Model.location
        bpy.ops.view3d.view_center_cursor()
        bpy.ops.view3d.viewnumpad(type = 'FRONT')
         
        self.splint.landmarks_set = True
        tracking.trackUsage("D3Splint:SplintLandmarks",None)

class D3SPLINT_OT_splint_paint_margin(bpy.types.Operator):
    '''Use dyntopo sculpt to add/remove detail at margin'''
    bl_idname = "d3splint.splint_paint_margin"
    bl_label = "Paint Splint Margin"
    bl_options = {'REGISTER','UNDO'}

    #splint thickness
    detail = bpy.props.FloatProperty(name="Detail", description="Edge length detail", default=.8, min=.025, max=1, options={'ANIMATABLE'})
    
    
    @classmethod
    def poll(cls, context):
        return True
            
    def execute(self, context):
        
            
        settings = odcutils.get_settings()
   
        
        j = context.scene.odc_splint_index
        splint =context.scene.odc_splints[j]
        if splint.model in bpy.data.objects:
            model = bpy.data.objects[splint.model]
        else:
            print('whoopsie...margin and model not defined or something is wrong')
            return {'CANCELLED'}
        
        for ob in context.scene.objects:
            ob.select = False
        
                
        model.hide = False
        model.select = True
        context.scene.objects.active = model
        
            
        bpy.ops.object.mode_set(mode = 'SCULPT')
        bpy.ops.view3d.viewnumpad(type = 'RIGHT')
        #if not model.use_dynamic_topology_sculpting:
        #    bpy.ops.sculpt.dynamic_topology_toggle()
        
        scene = context.scene
        paint_settings = scene.tool_settings.unified_paint_settings
        paint_settings.use_locked_size = True
        paint_settings.unprojected_radius = .5
        brush = bpy.data.brushes['Mask']
        brush.strength = 1
        brush.stroke_method = 'LINE'
        scene.tool_settings.sculpt.brush = brush
        
        bpy.ops.brush.curve_preset(shape = 'MAX')
        
        return {'FINISHED'}
    
class D3SPLINT_OT_splint_trim_model_paint(bpy.types.Operator):
    """Trim model from painted boundary"""
    bl_idname = "d3splint.splint_trim_from_paint"
    bl_label = "Trim Model From Paint"
    bl_options = {'REGISTER','UNDO'}

    invert = bpy.props.BoolProperty(default = False, name = 'Invert')
    @classmethod
    def poll(cls, context):
        
        c1 = context.object.type == 'MESH'
        c2 = context.mode == 'SCULPT'
        return c1 & c2
    
    def execute(self, context):
        
        splint = context.scene.odc_splints[0]
        model = context.scene.odc_splints[0].model
        Model = bpy.data.objects.get(model)
        if not Model:
            self.report({'ERROR'}, "Need to set Model first")
        
        
        mx = Model.matrix_world
        bme = bmesh.new()
        bme.from_mesh(Model.data)

        bme.verts.ensure_lookup_table()
        bme.edges.ensure_lookup_table()
        bme.faces.ensure_lookup_table()
        
        
        mask = bme.verts.layers.paint_mask.verify()
        
        #clean loose verts
        mask_verts = []
        for v in bme.verts:
            if v[mask] > 0.1:
                mask_verts.append(v)
        
        
        mask_set_verts = set(mask_verts)
        
        
        ### TODO GOOD ERROR CONDITIONS###
        total_faces = set(bme.faces[:])
        mask_faces = set([f for f in bme.faces if all([v in mask_set_verts for v in f.verts])])
        total_faces.difference_update(mask_faces)
        
        
        print('there are %i faces in the mesh' % len(bme.faces))
        print('there are %i faces in the mask' % len(mask_faces))
        print('there are %i other faces' % len(total_faces))
        
        
        
        ###TODO, make the flood selection work with sets not just BME###
        mask_islands = []
        iters = 0
        while len(mask_faces) and iters < 100:
            iters += 1
            seed = mask_faces.pop()
            island = flood_selection_faces_limit(bme, {}, seed, mask_faces, max_iters = 10000)
            
            print('iteration %i with %i mask island faces' % (iters, len(island)))
            mask_islands.append(island)
            mask_faces.difference_update(island)
            
        
        print('there are %i mask islands' % len(mask_islands))    
        
        mask_islands.sort(key = len)
        mask_islands.reverse()
        mask_faces = mask_islands[0]
        
        print('there are %i faces in the largest mask' % len(mask_faces))
        
        if len(mask_islands) > 1 and len(mask_islands[1]) != 0:
            seed_faces = mask_islands[1]
            seed_face = seed_faces.pop()
            best = flood_selection_faces(bme, mask_faces, seed_face, max_iters = 10000)
        
        else:
            islands = []
            iters = 0
            while len(total_faces) and iters < 100:
                iters += 1
                seed = total_faces.pop()
                island = flood_selection_faces(bme, mask_faces, seed, max_iters = 10000)
                
                print('iteration %i with %i island faces' % (iters, len(island)))
                islands.append(island)
                total_faces.difference_update(island)
                
            print('there are %i islands' % len(islands))
            best = max(islands, key = len)
        
        total_faces = set(bme.faces[:])
        del_faces = total_faces - best
        
        
        if len(del_faces) == 0:
            print('ERROR because we are not deleting any faces')
            #reset the mask for the small mask islands
            if len(mask_islands) > 1:
                for isl in mask_islands[1:]:
                    print('fixing %i faces in mask island' % len(isl))
                    for f in isl:
                        for v in f.verts:
                            v[mask] = 0
            
            
            bme.to_mesh(Model.data)
            Model.data.update()
        
            bme.free()
            self.report({'WARNING'}, 'Unable to trim, undo, then ensure your paint loop is closed and try again')
            return {'FINISHED'}
        
        
        print('deleting %i faces' % len(del_faces))
        bmesh.ops.delete(bme, geom = list(del_faces), context = 3)
        del_verts = []
        for v in bme.verts:
            if all([f in del_faces for f in v.link_faces]):
                del_verts += [v]        
        bmesh.ops.delete(bme, geom = del_verts, context = 1)
        print('deleteing %i verts' % len(del_verts))
        
        del_edges = []
        for ed in bme.edges:
            if len(ed.link_faces) == 0:
                del_edges += [ed]
        
        bmesh.ops.delete(bme, geom = del_edges, context = 4) 
        
        trimmed_model = bpy.data.meshes.new('Trimmed_Model')
        trimmed_obj = bpy.data.objects.new('Trimmed_Model', trimmed_model)
        bme.to_mesh(trimmed_model)
        trimmed_obj.matrix_world = mx
        context.scene.objects.link(trimmed_obj)
        
        
        new_edges = [ed for ed in bme.edges if len(ed.link_faces) == 1]
        
    
        for i in range(10):        
            gdict = bmesh.ops.extrude_edge_only(bme, edges = new_edges)
            bme.edges.ensure_lookup_table()
            bme.verts.ensure_lookup_table()
            new_verts = [ele for ele in gdict['geom'] if isinstance(ele, bmesh.types.BMVert)]
            new_edges = [ele for ele in gdict['geom'] if isinstance(ele, bmesh.types.BMEdge)]
            for v in new_verts:
                v.co += .4 * Vector((0,0,1))
        v_max = max(new_verts, key = lambda x: x.co[2])
        z_max = v_max.co[2]
        loops = edge_loops_from_bmedges(bme, [ed.index for ed in new_edges])
        print('there are %i loops' % len(loops))
        for loop in loops:
            for i in loop:
                bme.verts[i].co[2] = z_max
            if loop[0] != loop[-1]:continue
            loop.pop()
            f = [bme.verts[i] for i in loop]
            if len(set(f)) == len(f):
                bme.faces.new(f)
            
        bmesh.ops.recalc_face_normals(bme,faces = bme.faces[:])
            
        based_model = bpy.data.meshes.new('Based_Model')
        based_obj = bpy.data.objects.new('Based_Model', based_model)
        bme.to_mesh(based_model)
        based_obj.matrix_world = mx
        context.scene.objects.link(based_obj)
        
        Model.hide = True    
                    
        bme.free()
        
        
        return {'FINISHED'}

def pick_model_callback(self, context):
    self.help_box.draw()
    
class D3SPLINT_OT_pick_model(bpy.types.Operator):
    """Left Click on Model to Build Splint"""
    bl_idname = "d3splint.pick_model"
    bl_label = "Pick Model"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls,context):
        return True
    
    def modal_nav(self, event):
        events_nav = {'MIDDLEMOUSE', 'WHEELINMOUSE','WHEELOUTMOUSE', 'WHEELUPMOUSE','WHEELDOWNMOUSE'} #TODO, better navigation, another tutorial
        handle_nav = False
        handle_nav |= event.type in events_nav

        if handle_nav: 
            return 'nav'
        return ''
    
    def modal_main(self,context,event):
        # general navigation
        nmode = self.modal_nav(event)
        if nmode != '':
            return nmode  #stop here and tell parent modal to 'PASS_THROUGH'

        
        if event.type == 'MOUSEMOVE':
            self.hover_scene(context, event.mouse_region_x, event.mouse_region_y)    
            return 'main'
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            
            return self.pick_model(context)
        
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            return 'cancel' 

        return 'main'
    


    def modal(self, context, event):
        context.area.tag_redraw()
        
        FSM = {}    
        FSM['main']    = self.modal_main
        FSM['nav']     = self.modal_nav
        
        nmode = FSM[self.mode](context, event)
        
        if nmode == 'nav': 
            return {'PASS_THROUGH'}
        
        if nmode in {'finish','cancel'}:
            #clean up callbacks
            context.window.cursor_modal_restore()
            context.area.header_text_set()
            context.user_preferences.themes[0].view_3d.outline_width = self.outline_width
        
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}
        
        if nmode: self.mode = nmode
        
        return {'RUNNING_MODAL'}

    def hover_scene(self,context,x, y):
        scene = context.scene
        region = context.region
        rv3d = context.region_data
        coord = x, y
        ray_max = 10000
        view_vector = region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = region_2d_to_origin_3d(region, rv3d, coord)
        ray_target = ray_origin + (view_vector * ray_max)

        if bversion() <= '002.076.000':
            result, ob, mx, loc, normal = scene.ray_cast(ray_origin, ray_target)
        else:
            result, loc, normal, idx, ob, mx = scene.ray_cast(ray_origin, ray_target)

        if result:
            self.ob = ob
            self.ob_preview = ob.name
            context.area.header_text_set(ob.name)
            
            for obj in context.scene.objects:
                if obj != ob:
                    obj.select = False
                else:
                    obj.select = True
        
        else:
            self.ob = None
            self.ob_preview = 'None'
            context.area.header_text_set('None')
            for ob in context.scene.objects:
                ob.select = False
            if context.object:
                context.scene.objects.active = None
    
    def pick_model(self, context):
        
        prefs = odcutils.get_settings()
        if self.ob == None:
            return 'main'
        
        n = context.scene.odc_splint_index
        if len(context.scene.odc_splints) != 0:
            
            odc_splint = context.scene.odc_splints[n]
            odc_splint.model = self.ob.name
            odc_splint.model_set = True
            
        else:
            my_item = context.scene.odc_splints.add()        
            my_item.name = 'Splint'
            my_item.model = self.ob.name
            my_item.model_set = True
            
            my_item.jaw_type = prefs.default_jaw_type
            
        if "Model Mat" not in bpy.data.materials:
            mat = bpy.data.materials.new('Model Mat')
            mat.diffuse_color = Color((0.5, .8, .4))
        else:
            mat = bpy.data.materials.get('Box Mat')
        
        # Assign it to object
        if self.ob.data.materials:
            # assign to 1st material slot
            self.ob.data.materials[0] = mat
        else:
            # no slots
            self.ob.data.materials.append(mat)    
            
        tracking.trackUsage("D3Splint:PickModel")
        return 'finish'
            
    def invoke(self,context, event):
        
        self.outline_width = context.user_preferences.themes[0].view_3d.outline_width
        context.user_preferences.themes[0].view_3d.outline_width = 4
        
        self.ob_preview = 'None'
        context.window.cursor_modal_set('EYEDROPPER')
        
        #TODO, tweak the modifier as needed
        help_txt = "Pick Model\n\n Hover over objects in the scene \n left click on model that splint will build on \n ESC to cancel"
        self.help_box = TextBox(context,500,500,300,200,10,20,help_txt)
        self.help_box.snap_to_corner(context, corner = [1,1])
        self.mode = 'main'
        self._handle = bpy.types.SpaceView3D.draw_handler_add(pick_model_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self) 
        
        tracking.trackUsage("D3Splint:MarkOutline", None)
        return {'RUNNING_MODAL'}
   
class D3SPLINT_OT_pick_opposing(bpy.types.Operator):
    """Left Click on Model to mark the opposing"""
    bl_idname = "d3splint.pick_opposing"
    bl_label = "Pick Opposing"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls,context):
        if len(context.scene.odc_splints) == 0:
            return False
        return True
    
    def modal_nav(self, event):
        events_nav = {'MIDDLEMOUSE', 'WHEELINMOUSE','WHEELOUTMOUSE', 'WHEELUPMOUSE','WHEELDOWNMOUSE'} #TODO, better navigation, another tutorial
        handle_nav = False
        handle_nav |= event.type in events_nav

        if handle_nav: 
            return 'nav'
        return ''
    
    def modal_main(self,context,event):
        # general navigation
        nmode = self.modal_nav(event)
        if nmode != '':
            return nmode  #stop here and tell parent modal to 'PASS_THROUGH'

        
        if event.type == 'MOUSEMOVE':
            self.hover_scene(context, event.mouse_region_x, event.mouse_region_y)    
            return 'main'
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            
            return self.pick_model(context)
        
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            return 'cancel' 

        return 'main'
    


    def modal(self, context, event):
        context.area.tag_redraw()
        
        FSM = {}    
        FSM['main']    = self.modal_main
        FSM['nav']     = self.modal_nav
        
        nmode = FSM[self.mode](context, event)
        
        if nmode == 'nav': 
            return {'PASS_THROUGH'}
        
        if nmode in {'finish','cancel'}:
            #clean up callbacks
            context.window.cursor_modal_restore()
            context.area.header_text_set()
            context.user_preferences.themes[0].view_3d.outline_width = self.outline_width
        
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}
        
        if nmode: self.mode = nmode
        
        return {'RUNNING_MODAL'}

    def hover_scene(self,context,x, y):
        scene = context.scene
        region = context.region
        rv3d = context.region_data
        coord = x, y
        ray_max = 10000
        view_vector = region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = region_2d_to_origin_3d(region, rv3d, coord)
        ray_target = ray_origin + (view_vector * ray_max)

        if bversion() <= '002.076.000':
            result, ob, mx, loc, normal = scene.ray_cast(ray_origin, ray_target)
        else:
            result, loc, normal, idx, ob, mx = scene.ray_cast(ray_origin, ray_target)

        if result:
            self.ob = ob
            self.ob_preview = ob.name
            context.area.header_text_set(ob.name)
            
            for obj in context.scene.objects:
                if obj != ob:
                    obj.select = False
                else:
                    obj.select = True
        
        else:
            self.ob = None
            self.ob_preview = 'None'
            context.area.header_text_set('None')
            for ob in context.scene.objects:
                ob.select = False
            if context.object:
                context.scene.objects.active = None
    
    def pick_model(self, context):
        
        if self.ob == None:
            return 'main'
            
        n = context.scene.odc_splint_index
        odc_splint = context.scene.odc_splints[n]
        odc_splint.opposing = self.ob.name
        odc_splint.opposing_set = True
         
        if "Opposing Mat" not in bpy.data.materials:
            mat = bpy.data.materials.new('Opposing Mat')
            mat.diffuse_color = Color((0.4, .5, .6))
        else:
            mat = bpy.data.materials.get('Opposing Mat')
        
        # Assign it to object
        if self.ob.data.materials:
            # assign to 1st material slot
            self.ob.data.materials[0] = mat
        else:
            # no slots
            self.ob.data.materials.append(mat) 
            
        tracking.trackUsage("D3Splint:SetOpposing")
        return 'finish'
            
    def invoke(self,context, event):
        
        if not len(context.scene.odc_splints):
            self.report({'ERROR'}, 'Need to set master model first')
            return('CANCELLED')
        
        
        n = context.scene.odc_splint_index
        odc_splint = context.scene.odc_splints[n]
        
        Model = bpy.data.objects.get(odc_splint.model)
        if not Model:
            self.report({'ERROR'}, 'Need to set master model first')
            return('CANCELLED')
        
        self.outline_width = context.user_preferences.themes[0].view_3d.outline_width
        context.user_preferences.themes[0].view_3d.outline_width = 4
        
        self.ob_preview = 'None'
        context.window.cursor_modal_set('EYEDROPPER')
        
        #TODO, tweak the modifier as needed
        help_txt = "Pick Model\n\n Hover over objects and left click on opposing model\n ESC to cancel"
        self.help_box = TextBox(context,500,500,300,200,10,20,help_txt)
        self.help_box.snap_to_corner(context, corner = [1,1])
        self.mode = 'main'
        self._handle = bpy.types.SpaceView3D.draw_handler_add(pick_model_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self) 
        
        tracking.trackUsage("D3Splint:PickOpposing", None)
        return {'RUNNING_MODAL'}     
def register():
    bpy.utils.register_class(D3SPLINT_OT_splint_land_marks)
    bpy.utils.register_class(D3SPLINT_OT_splint_paint_margin)  
    bpy.utils.register_class(D3SPLINT_OT_splint_trim_model_paint)
    bpy.utils.register_class(D3SPLINT_OT_splint_occlusal_arch_max)
    bpy.utils.register_class(D3SPLINT_OT_pick_model)
    bpy.utils.register_class(D3SPLINT_OT_pick_opposing)
     
def unregister():
    bpy.utils.unregister_class(D3SPLINT_OT_splint_land_marks)
    bpy.utils.unregister_class(D3SPLINT_OT_splint_paint_margin)
    bpy.utils.unregister_class(D3SPLINT_OT_splint_trim_model_paint)
    bpy.utils.unregister_class(D3SPLINT_OT_splint_occlusal_arch_max)
    bpy.utils.unregister_class(D3SPLINT_OT_pick_model)
    bpy.utils.unregister_class(D3SPLINT_OT_pick_opposing)
    
if __name__ == "__main__":
    register()