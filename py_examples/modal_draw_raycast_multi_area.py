'''
Copyright (c) 2014-2016 Patrick Moore
patrick.moore.bu@gmail.com

Created by Patrick Moore for Blender

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''




import numpy as np
from numpy.ma.core import fmod
import math
import time


import bpy
import blf
import bgl
from bpy.types import Operator
from bpy.props import FloatVectorProperty, StringProperty, IntProperty, BoolProperty, FloatProperty, EnumProperty
from bpy.types import Operator
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_location_3d, region_2d_to_origin_3d, region_2d_to_vector_3d
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree


#### UTILITIES AND WRAPPERS  ####

def tag_redraw_all_view3d(context):
    # Py cant access notifers
    #iterate through and tag all 'VIEW_3D' regions
    #for drawing
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()



def draw_3d_points_specific_region(region, rv3d, points, color, size):
    '''
    draw a bunch of dots
    args:
        points: a list of 3d vectors
        color: tuple (r,g,b,a)
        size: integer? maybe a float
    '''
    points_2d = [location_3d_to_region_2d(region, rv3d, loc) for loc in points]
    if None in points_2d:
        points_2d = filter(None, points_2d)
    bgl.glColor4f(*color)
    bgl.glPointSize(size)
    bgl.glBegin(bgl.GL_POINTS)
    for coord in points_2d:
        #TODO:  Debug this problem....perhaps loc_3d is returning points off of the screen.
        if coord:
            bgl.glVertex2f(*coord)  

    bgl.glEnd()   
    return
#### Custom Classes####
                 
### Draw Code To Lable Regions ###    
def draw_callback_px(self, context):

    for n, area in enumerate(self.areas):
        if context.area.x == area.x and context.area.y == area.y:  #then this is where our mouse is
            
            font_id = 0  # XXX, need to find out how best to get this.
            height = context.region.height
            width = context.region.width
            dims = blf.dimensions(0, self.messages[n])
            #blf.position(font_id, 10, height - 10 - dims[1], 0)  #top left
            blf.position(font_id, width - 10 - 2* dims[0], 10 + dims[1]/2, 0)
            
            blf.size(font_id, 20, 72)
            blf.draw(font_id, self.messages[n])
        
            if (self.mouse_raw[0] > area.x and self.mouse_raw[0] < area.x + area.width) and \
                (self.mouse_raw[1] > area.y and self.mouse_raw[1] < area.y + area.height):
                #label the mouse
                dims = blf.dimensions(0,'MOUSE %i' %n)
                x = self.mouse_region_coord[0] - .5 * dims[0]
                y = self.mouse_region_coord[1] + dims[1]
                blf.position(font_id,x,y,0)
                blf.draw(font_id,'MOUSE %i' % n)
        
    
            if len(self.area_data[n]):
                N = len(self.areas)
                color = (n/N, .5*n/N, (1-n/N), 1)
                draw_3d_points_specific_region(context.region, context.space_data.region_3d, self.area_data[n], color, 3)
            
def draw_callback_3d(self,context):
    pass
    
class VIEW3D_OT_explore_multi_view3d(Operator):
    """Interact and Draw in Multiple Regions"""
    bl_idname = "view3d.explore_multi_views"
    bl_label = "Explore Multi View"

    @classmethod
    def poll(cls, context):
        
        return True

    def modal(self, context, event):
        
        tag_redraw_all_view3d(context)
        FSM = {}
        FSM['nav']  = self.modal_nav
        FSM['wait'] = self.modal_wait
        
        nmode = FSM[self.mode](context, event)
        
        if nmode == 'nav': 
            return {'PASS_THROUGH'}
        
        if nmode in {'finish','cancel'}:
            #clean up callbacks
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            return {'FINISHED'} if nmode == 'finish' else {'CANCELLED'}
        
        if nmode: self.mode = nmode
        
        return {'RUNNING_MODAL'}   
        
    def modal_nav(self, context, event):
        '''
        Determine/handle navigation events.
        FSM passes control through to underlying panel if we're in 'nav' state
        '''
 
        handle_nav = False
        handle_nav |= event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE','MIDDLEMOUSE'}
        
        if handle_nav:
            self.post_update   = True
            self.is_navigating = True
            return 'wait' if event.value =='RELEASE' else 'nav'

        self.is_navigating = False
        return ''
       
    def modal_wait(self, context, event):
        
        # general navigation
        nmode = self.modal_nav(context, event)
        if nmode != '':
            return nmode  #stop here and tell parent modal to 'PASS_THROUGH'
        
        #TODO, tag redraw current if only needing to redraw that single window
        #depends on what information you are changing
        
        if event.type == 'MOUSEMOVE':
            
            #get the appropriate region and region_3d for ray_casting
            #also, important because this is what your blf and bgl
            #wrappers are going to draw in at that moment
            for area in self.areas:
                if (event.mouse_x > area.x and event.mouse_x < area.x + area.width) and \
                    (event.mouse_y > area.y and event.mouse_y < area.y + area.height):
                
                    for reg in area.regions:
                        if reg.type == 'WINDOW':
                            region = reg
                    for spc in area.spaces:
                        if spc.type == 'VIEW_3D':
                            rv3d = spc.region_3d
                
                    #just transform the mouse window coords into the region coords        
                    coord_region = (event.mouse_x - region.x, event.mouse_y - region.y)
                    
        
                    self.mouse_region_coord = coord_region
                    self.mouse_raw = (event.mouse_x, event.mouse_y)
                    
            return 'wait'
        
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            
            #get the appropriate region and region_3d for ray_casting
            for n, area in enumerate(self.areas):
                if (event.mouse_x > area.x and event.mouse_x < area.x + area.width) and \
                    (event.mouse_y > area.y and event.mouse_y < area.y + area.height):
                
                    for reg in area.regions:
                        if reg.type == 'WINDOW':
                            region = reg
                    for spc in area.spaces:
                        if spc.type == 'VIEW_3D':
                            rv3d = spc.region_3d
                
                    #just transform the mouse window coords into the region coords        
                    coord_region = (event.mouse_x - region.x, event.mouse_y - region.y)
                    
        
                    self.mouse_region_coord = coord_region
                    self.mouse_raw = (event.mouse_x, event.mouse_y)
                    
                    #this is the important part, using the correct region and rv3d
                    #to get the ray.
                    view_vector = region_2d_to_vector_3d(region, rv3d, coord_region)
                    ray_origin = region_2d_to_origin_3d(region, rv3d, coord_region)
                    ray_target = ray_origin + (view_vector * 10000)
                
                    res, loc, no, ind, obj, mx = context.scene.ray_cast(ray_origin, view_vector)

                    if res:
                        print('Clicked on ' + obj.name + ' in the %i region' % n)
                        self.area_data[n] += [loc]
                             
            return 'wait'
        
        elif event.type == 'ESC':
            return 'cancel'
        
        return 'wait'
    
    def invoke(self, context, event):
       
        #collect all the 3d_view regions
        #this can be done with other types
        
        self.mode = 'wait'
        
        self.areas = []
        self.area_data = []
        self.messages = []
        self.regions = []
        
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    self.areas += [area]
                    self.area_data += [[]] #empy list to be filled with 3d points
                    for region in area.regions:
                        if region.type == 'WINDOW': #ignore the tool-bar, header etc
                            self.regions += [region]
                            self.messages += ['Region %i' % len(self.messages)]
        
        if len(self.areas) == 0:
            #error message
            return {'CANCELLED'}
       
        self.mouse_screen_coord = (0,0)
        context.window_manager.modal_handler_add(self)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(draw_callback_px, (self, context), 'WINDOW', 'POST_PIXEL')
        return {'RUNNING_MODAL'}
                   

def register():
    bpy.utils.register_class(VIEW3D_OT_explore_multi_view3d)

def unregister():
    bpy.utils.unregister_class(VIEW3D_OT_explore_multi_view3d)


if __name__ == "__main__":
    register()