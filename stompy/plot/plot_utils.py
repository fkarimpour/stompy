from __future__ import division
from __future__ import print_function
from builtins import str
from builtins import zip
from builtins import range
from builtins import object
from past.utils import old_div
from safe_pylab import *
import time
from matplotlib.collections import LineCollection
from matplotlib.transforms import Transform,Affine2D
import matplotlib.transforms as transforms
from matplotlib import collections, path
from matplotlib import pyplot as pl
from matplotlib.patches import Rectangle
from matplotlib.tri import Triangulation
import numpy as np
import utils
from six import string_types


try:
    import xarray as xr
except ImportError:
    xr="XARRAY NOT AVAILABLE"

# convenience function for getting coordinates from the plot:
def pick_points(n):
    count = [0]
    pick_points.results = zeros( (n,2), float64)

    fig = gcf()
    cid = None
    
    
    def click_handler(event):
        print('button=%d, x=%d, y=%d, xdata=%f, ydata=%f'%(
            event.button, event.x, event.y, event.xdata, event.ydata))
        if event.xdata:
            pick_points.results[count[0]] = [event.xdata, event.ydata]
            count[0] += 1
            if count[0] >= n:
                fig.canvas.mpl_disconnect(cid)
            

    cid = fig.canvas.mpl_connect('button_press_event', click_handler)

# A rehash of pick_points:
from array_append import array_append
def ax_picker(ax):
    fig = ax.figure
    
    if hasattr(ax,'pick_cids'):
        for cid in ax.pick_cids:
            fig.canvas.mpl_disconnect(cid)

    def init_picked():
        ax.picked = zeros( (0,4), float64)
        ax.pick_start = None
    init_picked()
    
    def on_press(event):
        if fig.canvas.toolbar.mode != '':
            return
        if event.button==1 and event.xdata:
            ax.pick_start = [event.xdata,event.ydata]
        elif event.button==3:
            print(ax.picked)
            init_picked()
    def on_release(event):
        if fig.canvas.toolbar.mode != '':
            return
        if event.xdata and ax.pick_start is not None:
            new_pnt = array([ax.pick_start[0],event.xdata,ax.pick_start[1],event.ydata])
            ax.picked=array_append( ax.picked,new_pnt )

    cid_p = fig.canvas.mpl_connect('button_press_event', on_press)
    cid_r = fig.canvas.mpl_connect('button_release_event', on_release)
    ax.pick_cids = [cid_p,cid_r]

def draw_polyline(ax=None,remove=True):
    ax=ax or plt.gca()
    fig=ax.get_figure()

    collecting=[1]
    pick_points=[]

    line=ax.plot([],[],'r-o')[0]

    def click_handler(event):
        if fig.canvas.toolbar.mode != '':
            return
        print('button=%d, x=%d, y=%d, xdata=%f, ydata=%f'%(
            event.button, event.x, event.y, event.xdata, event.ydata))

        if event.button==1 and event.xdata:
            pick_points.append( [event.xdata,event.ydata] )
            x=[p[0] for p in pick_points]
            y=[p[1] for p in pick_points]
            line.set_xdata(x)
            line.set_ydata(y)
        elif event.button==3:
            print("Done collecting points")
            collecting[0]=0

    cid = fig.canvas.mpl_connect('button_press_event', click_handler)
    while collecting[0]:
        plt.pause(0.01)
    fig.canvas.mpl_disconnect(cid)
    if remove:
        ax.lines.remove(line)
        plt.draw()
    return np.array(pick_points)

    

def plotyy( x1, y1, x2, y2, color1='b', color2='g', fun=None, **kwargs ):
    """
    A work-alike of the Matlab (TM) function of the same name.  This
    places two curves on the same axes using the same x-axis, but
    different y-axes.

    Call signature::

    ax, h1, h2 = plotyy( x1, y2, x2, y2, color1='b', color2='g',
                         fun=None, **kwargs )

    color1 and color2 are the colors to make respective curves and y-axes.

    fun is the function object to use for plotting.  Must accept calls
    of the form fun(x,y,color='color',**kwargs).  Typically, something
    like plot, semilogy, semilogx or loglog.  If *None*, defaults to
    pyplot.plot.

    **kwargs is any list of keyword arguments accepted by fun.

    ax is a 2 element list with the handles for the first and second
    axes.  h1 is the handle to the first curve, h2 to the second
    curve.

    NOTE that this function won't scale two curves so that y-ticks are
    in the same location as the Matlab (TM) version does.
    """
    if fun == None: fun = plot

    ax1 = gca()
    ax1.clear()

    # Get axes location
    try:
        rect = ax1.get_position().bounds
    except AttributeError:
        rect = array( ax1.get_position() )
        rect[2:] += rect[:2]

    # Add first curve
    h1 = fun( x1, y1, color=color1, **kwargs )

    # Add second axes on top of first with joined x-axis
    ax2 = twinx(ax1)

    # Plot second curve initially
    h2 = fun( x2, y2, color=color2, **kwargs )

    # Set axis properties
    setp( ax2.get_xticklabels(), visible=False)

    # Change colors appropriately
    def recolor( obj, col ):
        try: obj.set_color( col )
        except: pass
        try: obj.set_facecolor( col )
        except: pass
        try: obj.set_edgecolor( col )
        except: pass
        try:
            ch = obj.get_children()
            for c in ch:
                recolor( c, col )
        except: pass

    recolor( ax1.yaxis, color1 )
    recolor( ax2.yaxis, color2 )

    draw_if_interactive()

    return ( [ax1,ax2], h1, h2 ) 


if 0:
    def dump_figure(fname,fig=None):
        """ Save as much of the info about a figure as possible, such that
        it can be replayed later, without dependence on the original data
        but with zoom-able interactions.
        """
        if fig is None:
            fig = gcf()


    # testing for dump_figure:
    figure(1)


        



# remove parts of the plot that extend beyond the x limits of the
# axis - assumes that the x-data for each line is non-decreasing
def trim_xaxis(ax=None):
    if ax is None:
        ax = gca()
        
    xmin,xmax,ymin,ymax = ax.axis()
    for line in ax.lines:
        xdata = line.get_xdata()
        ydata = line.get_ydata()

        i_start = searchsorted(xdata,xmin) - 1
        if i_start < 0:
            i_start = 0
        i_end = searchsorted(xdata,xmax) + 1

        xdata = xdata[i_start:i_end]
        ydata = ydata[i_start:i_end]

        line.set_xdata(xdata)
        line.set_ydata(ydata)
        

def plot_tri(tri,**kwargs):
    # DEPRECATED: matplotlib now has triplot and friends
    # compile list of edges, then create the collection, and plot
    
    ex = tri.x[tri.edge_db]
    ey = tri.y[tri.edge_db]
    edges = concatenate( (ex[:,:,newaxis], ey[:,:,newaxis]), axis=2)
    colors = ones( (len(edges),4), float32 )
    colors[:,:3] = 0
    colors[:,3] = 1.0
    
    coll = LineCollection(edges,colors=colors)

    ax = gca()
    ax.add_collection(coll)


def scalebar(xy,L=None,aspect=0.05,unit_factor=1,fmt="%.0f",label_txt=None,fractions=[0,0.5,1.0],
             ax=None,xy_transform=None,dy=None,
             style='altboxes'):
    """ Draw a simple scale bar with labels - bottom left
    is given by xy.  
    xy_transform: units for interpreting xy.  If not given
    """
    ax = ax or gca()

    if xy_transform is None:
        txt_trans=xy_transform=ax.transData
    else:
        # Still have to pull x scaling from the data axis
        xy_transform=ScaleXOnly(xy_transform,
                                ax.transData,xoffset=xy[0])
        txt_trans=xy_transform
        xy=[0,xy[1]] # x offset now rolled into xy_transform
    
    if L is None:
        xmin,xmax,ymin,ymax = ax.axis()
        L = 0.2 * (xmax - xmin)
    xmin,ymin = xy
    dx = L
    dy = dy or (aspect*L)
    # xmax = xmin + L
    ymax = ymin + dy

    objs = []
    txts = []

    if style in ('boxes','altboxes'):
        # one filled black box:
        objs.append( ax.fill([xmin,xmin+dx,xmin+dx,xmin],
                             [ymin,ymin,ymax,ymax],
                             'k', edgecolor='k',transform=xy_transform) )
        for i in range(len(fractions)-1):
            xleft=xmin+dx*fractions[i]
            xright=xmin+dx*fractions[i+1]
            xlist=[xleft,xright,xright,xleft]

            if style=='altboxes':
                ybot=ymin+0.5*(i%2)*dy
                ytop=ybot+0.5*dy
                # print ybot,ytop
                objs.append( ax.fill(xlist,
                                     [ybot,ybot,ytop,ytop],
                                     'w', edgecolor='k',transform=xy_transform) )
            else:
                if y%2==0:
                    objs.append( ax.fill(xlist,
                                         [ymin,ymin,ymax,ymax],
                                         'w', edgecolor='k',transform=xy_transform) )
    baseline=ymax + 0.25*dy
    for frac in fractions:
        frac_txt=fmt%(unit_factor* frac*L)
        txts.append( ax.text(xmin+frac*dx,baseline,
                             frac_txt,
                             ha='center',
                             transform=txt_trans)
                 )
    # annotate(fmt%(unit_factor*L), [xmin+dx,ymax+0.25*dy], ha='center')

    # Really would like for the label to be on the same baseline
    # as the fraction texts, and typeset along with the last
    # label, but allowing the number of the last label to be
    # centered on its mark
    if label_txt:
        txts.append( ax.text(xmin+frac*dx,baseline," "*len(frac_txt) + label_txt,ha='left',
                             transform=txt_trans) )
    return objs,txts
        

def north_arrow(xy,L,ax=None,decl_east=0.0,transform=None,angle=0.0,width=0.1):
    ax=ax or plt.gca()
    transform=transform or ax.transData

    w=width*L

    xy=np.asarray(xy)

    pnts=np.array( [[0,0], # base of arrow
                    [0,L], # vertical stroke
                    [w,0.5*L], # outer hypotenuse
                    [0,0.55*L]] ) # barb
    tot_rot=angle-decl_east
    pnts=utils.rot(tot_rot*np.pi/180,pnts)
    pnts=pnts+xy

    tip=xy+utils.rot(tot_rot*np.pi/180,np.array( [0,1.02*L] ))

    obj=ax.fill( pnts[:,0],pnts[:,1],'k',transform=transform)
    txt=ax.text(tip[0],tip[1]," $\mathcal{N}$",transform=transform,ha='center',rotation=tot_rot)
    return obj,txt

def show_slopes(ax=None,slopes=[-5./3,-1],xfac=5,yfac=3):
    ax = ax or pl.gca()
    x = np.median( [l.get_xdata()[-1] for l in ax.lines] )
    y = np.max( [l.get_ydata()[-1] for l in ax.lines] )

    y *= yfac # set the legend above the plotted lines

    xs = np.array([x/xfac,x])

    for s in slopes:
        ys = np.array([y/xfac**s,y])
        ax.loglog(xs,ys,c='0.5')
        pl.annotate("%g"%s,[xs[0],ys[0]])


        
# interactive log-log slope widget:
class Sloper(object):
    def __init__(self,ax=None,slope=-5./3,xfac=5,yfac=3,xlog=True,ylog=True,x=None,y=None):
        self.slope = slope
        self.ax = ax or pl.gca()
        if x is None:
            x = np.median( [l.get_xdata()[-1] for l in self.ax.lines] )
        if y is None:
            y = np.max( [l.get_ydata()[-1] for l in self.ax.lines] )

        y *= yfac # set the legend above the plotted lines

        self.xlog = xlog
        self.ylog = ylog

        xs = np.array([x/xfac,x])
        ys = np.array([y/xfac**slope,y])

        if self.xlog and self.ylog:
            self.line = self.ax.loglog(xs,ys,c='0.5',picker=5)[0]
        elif not self.xlog and not self.ylog:
            self.line = self.ax.plot(xs,ys,c='0.5',picker=5)[0]

        self.text = self.ax.text(xs[0],1.5*ys[0],"%g"%self.slope,transform=self.ax.transData)
        
        self.ax.figure.canvas.mpl_connect('pick_event',self.onpick)

        self.drag = dict(cid=None,x=None,y=None)

        
    def onpick(self,event):
        thisline = event.artist
        xdata = thisline.get_xdata()
        ydata = thisline.get_ydata()
        ind = event.ind
        print('onpick points:', list(zip(xdata[ind], ydata[ind])))
        print(' mouse point: ', event.mouseevent.xdata,event.mouseevent.ydata)

        cid = self.ax.figure.canvas.mpl_connect('button_release_event',self.drag_end)

        if self.drag['cid'] is not None:
            self.ax.figure.canvas.mpl_disconnect(self.drag['cid'])
            
        self.drag = dict(cid=cid,x=event.mouseevent.xdata,y=event.mouseevent.ydata)

    yoff = 1.5
    def update_text_pos(self):
        x = self.line.get_xdata()[0]
        y = self.line.get_ydata()[0]
        self.text.set_x(x)
        if self.ylog:
            self.text.set_y(self.yoff*y)
        else:
            self.text.set_y(self.yoff+y)
        
    def drag_end(self,event):
        print("drag end")
        self.ax.figure.canvas.mpl_disconnect(self.drag['cid'])
        xdata = self.line.get_xdata()
        ydata = self.line.get_ydata()
        
        if self.xlog:
            xdata *= event.xdata / self.drag['x']
        else:
            xdata += (event.xdata - self.drag['x'])
        if self.ylog:
            ydata *= event.ydata / self.drag['y']
        else:
            ydata += event.ydata - self.drag['y']
        self.line.set_xdata(xdata)
        self.line.set_ydata(ydata)
        self.update_text_pos()
        event.canvas.draw()


class LogLogSlopeGrid(object):
    """ draw evenly spaced lines, for now in log-log space, at a given slope.
    y=mx+b
    """
    def __init__(self,ax=None,slopes=[-5/3.],intervals=[10],xmin=None,xmax=None):
        """ Note that intervals is linear!  
        """
        self.ax = ax or pl.gca()
        self.slopes = slopes
        self.intervals = intervals
        self.colls = []
        self.xlog = self.ylog = True
        self.xmin=xmin
        self.xmax=xmax
        self.draw()
    def draw(self):
        for c in self.colls:
            self.ax.collections.remove(c)
        self.colls = []
        xmin,xmax,ymin,ymax = self.ax.axis()
        # allow override
        if self.xmin is not None:
            xmin=self.xmin 
        if self.xmax is not None:
            xmax=self.xmax 
        if self.xlog:
            xmin = np.log(xmin) ; xmax = np.log(xmax)
        if self.ylog:
            ymin = np.log(ymin) ; ymax = np.log(ymax)
            
        for s,interval in zip(self.slopes,self.intervals):
            corners = np.array( [[xmin,ymin],
                                 [xmax,ymin],
                                 [xmax,ymax],
                                 [xmin,ymax]] )
            corner_b = corners[:,1] - s*corners[:,0]

            if self.ylog:
                interval = np.log(interval)
            all_b = np.arange(corner_b.min(),corner_b.max(),interval)
            segs = np.zeros( (len(all_b),2,2), np.float64)
            segs[:,0,0] = xmin
            segs[:,1,0] = xmax
            segs[:,0,1] = s*xmin+all_b
            segs[:,1,1] = s*xmax+all_b
            if self.xlog:
                segs[...,0] = np.exp(segs[...,0])
            if self.ylog:
                segs[...,1] = np.exp(segs[...,1])
                
            coll = LineCollection(segs,color='0.75',zorder=-10)
            self.ax.add_collection(coll)
            self.colls.append(coll)

            
def enable_picker(coll,ax=None,cb=None,points=5):
    """ minimal wrapper for selecting indexes from a collection, like a
    scatter plot.  cb gets the first index chosen, and a handful of kw arguments:
     ax: the axes
     coll: collection
     event: event
     dataxy: data coordinates for the selected item
     
    returns an object which when called always returns the most recent index chosen
    """
    ax = ax or coll.get_axes() # was pl.gca()
    coll.set_picker(points) # should be 5 points

    class dummy(object):
        idx = None
        def __call__(self):
            return self.idx
    my_dummy = dummy()
    def onpick(event):
        if event.artist == coll:
            idx = event.ind[0]
            my_dummy.idx = idx
            if cb:
                if hasattr(coll,'get_offsets'): # for scatter plots
                    dataxy=coll.get_offsets()[idx]
                elif hasattr(coll,'get_xydata'): # for lines
                    dataxy=coll.get_xydata()[idx]
                kws=dict(ax=ax,coll=coll,event=event,dataxy=dataxy)
                print("in onpick: kws:",kws)
                cb(idx,**kws)
            else:
                pass

    my_dummy.cid = ax.figure.canvas.mpl_connect('pick_event',onpick)
    return my_dummy

def tooltipper(coll,tips=None,ax=None,points=5,persist=False):
    """ similar to enable_picker, but displays a transient text box
    tips: either a callable, called as in enable_picker, which returns the string
     to display, or a list of strings, which will be indexed by idx from the 
     collection.
    tips calling convention: the idx as the first argument, plus keywords:
     ax: the axes
     coll: collection
     event: event
     dataxy: data coordinates for the selected item
     
    persist: if False, then only one tooltip is displayed at a time.  If true,
     each tip can be toggled by clicking the individual item.

    returns an object which when called always returns the most recent index chosen
    """
    ax = ax or coll.get_axes() 
    coll.set_picker(points) 

    def basic_tips(idx,**kws):
        return str(idx)
    if tips is None:
        tips=basic_tips

    class dummy(object):
        last_idx = None
        def __init__(self):
            self.texts={} # map index to Text
        def __call__(self):
            return self.last_idx
    my_dummy = dummy()
    def onpick(event):
        if event.artist == coll:
            idx = event.ind[0]

            if idx in my_dummy.texts: # toggle off
                ax.texts.remove(my_dummy.texts.pop(idx))
                ax.figure.canvas.draw()
                return
            
            if not persist: # also toggle off anybody currently shown
                for k,txt in my_dummy.texts.items():
                    ax.texts.remove(txt)
                self.texts={}
                
            if hasattr(coll,'get_offsets'): # for scatter plots
                xy=coll.get_offsets()[idx]
            elif hasattr(coll,'get_xydata'): # for lines
                xy=coll.get_xydata()[idx]
            else:
                print("Can't figure out xy location!")
                return
            kws=dict(ax=ax,coll=coll,event=event,dataxy=xy)
            tip_str=tips(idx,**kws)

            tt_text=ax.text(xy[0],xy[1],tip_str,
                            transform=ax.transData,
                            va='top',ha='left',
                            bbox=dict(facecolor=(1.0,1.0,0.5),ec='k',lw=0.5))
            my_dummy.texts[idx]=tt_text
            ax.figure.canvas.draw()
                
    my_dummy.cid = ax.figure.canvas.mpl_connect('pick_event',onpick)
    return my_dummy


def gpick(coll,*args,**kwargs):
    """ Given a collection, wait for a pick click, and return the id 
    of the picked object within the collection
    """
    picked_id=[-1]
    def my_cb(idx,**kwarg):
        picked_id[0]=idx
    def on_close(event):
        picked_id[0]=None
    
    fig=coll.get_figure()
    cid=fig.canvas.mpl_connect('close_event', on_close)

    
    picker=enable_picker(coll,cb=my_cb,**kwargs)
    while picked_id[0]==-1:
        plt.pause(0.01)
    fig.canvas.mpl_disconnect(cid)
    fig.canvas.mpl_disconnect(picker.cid)

    return picked_id[0]

def function_contours(f=lambda x,y: x-y,ax=None,Nx=20,Ny=20,V=10,
                      fmt=None):
    """ Cheap way to draw contours of a function and label them.
    Just evaluates the function on a grid and calls contour
    """
    ax = ax or pl.gca()
    xxyy = ax.axis()
    x = np.linspace(xxyy[0],xxyy[1],Nx)
    y = np.linspace(xxyy[2],xxyy[3],Ny)
    X,Y = np.meshgrid(x,y)
    Z = f(X,Y)
    ctr = pl.contour(X,Y,Z,V,colors='k')
    if fmt:
        ax.clabel(ctr,fmt=fmt)
        
    return ctr


from matplotlib import ticker
def sqrt_scale(mappable,cbar,fmt="%.2f"):
    mappable.set_array(np.sqrt(mappable.get_array()))

    def map_and_fmt(x,pos):
        return fmt%(x**2)
    cbar.formatter = ticker.FuncFormatter(map_and_fmt)
    cbar.update_ticks()

def period_labeler(freq,base_unit='h'):
    assert base_unit=='h' # or fix!
    if freq==0.0:
        return "DC"
    period_h=1./freq
    if period_h>30:
        return "%.2fd"%(period_h/24.)
    elif period_h>1:
        return "%.2fh"%(period_h)
    else:
        return "%.2fm"%(period_h*60)

def period_scale(xaxis,base_unit='h'):
    def flabel(f_per_h,pos):
        return period_labeler(f_per_h,base_unit)
    fmter=FuncFormatter(flabel)
    xaxis.set_major_formatter(fmter)


def pad_pcolormesh(X,Y,Z,ax=None,dx_single=None,dy_single=None,**kwargs):
    """ Rough expansion of X and Y to be the bounds of
    cells, rather than the middles. Reduces the shift error
    in the plot.
    dx_single: if there is only one sample in x, use this for width
    dy_single: if there is only one sample in y, use this for height
    """
    Xpad,Ypad=utils.center_to_edge_2d(X,Y,dx_single=dx_single,dy_single=dy_single)
    ax=ax or plt.gca()
    return ax.pcolormesh(Xpad,Ypad,Z,**kwargs)


def show_slopes(ax=None,slopes=[-5./3,-1],xfac=5,yfac=3):
    ax = ax or pl.gca()
    x = np.median( [l.get_xdata()[-1] for l in ax.lines] )
    y = np.max( [l.get_ydata()[-1] for l in ax.lines] )

    y *= yfac # set the legend above the plotted lines

    xs = np.array([x/xfac,x])

    for s in slopes:
        ys = np.array([y/xfac**s,y])
        ax.loglog(xs,ys,c='0.5')
        pl.annotate("%g"%s,[xs[0],ys[0]])


        
# interactive log-log slope widget:
class Sloper(object):
    def __init__(self,ax=None,slope=-5./3,xfac=5,yfac=3,xlog=True,ylog=True,x=None,y=None):
        self.slope = slope
        self.ax = ax or pl.gca()
        if x is None:
            x = np.median( [l.get_xdata()[-1] for l in self.ax.lines] )
        if y is None:
            y = np.max( [l.get_ydata()[-1] for l in self.ax.lines] )

        y *= yfac # set the legend above the plotted lines

        self.xlog = xlog
        self.ylog = ylog

        xs = np.array([x/xfac,x])
        ys = np.array([y/xfac**slope,y])

        if self.xlog and self.ylog:
            self.line = self.ax.loglog(xs,ys,c='0.5',picker=5)[0]
        elif not self.xlog and not self.ylog:
            self.line = self.ax.plot(xs,ys,c='0.5',picker=5)[0]

        self.text = self.ax.text(xs[0],1.5*ys[0],"%g"%self.slope,transform=self.ax.transData)
        
        self.ax.figure.canvas.mpl_connect('pick_event',self.onpick)

        self.drag = dict(cid=None,x=None,y=None)

        
    def onpick(self,event):
        thisline = event.artist
        xdata = thisline.get_xdata()
        ydata = thisline.get_ydata()
        ind = event.ind
        print('onpick points:', list(zip(xdata[ind], ydata[ind])))
        print(' mouse point: ', event.mouseevent.xdata,event.mouseevent.ydata)

        cid = self.ax.figure.canvas.mpl_connect('button_release_event',self.drag_end)

        if self.drag['cid'] is not None:
            self.ax.figure.canvas.mpl_disconnect(self.drag['cid'])
            
        self.drag = dict(cid=cid,x=event.mouseevent.xdata,y=event.mouseevent.ydata)

    yoff = 1.5
    def update_text_pos(self):
        x = self.line.get_xdata()[0]
        y = self.line.get_ydata()[0]
        self.text.set_x(x)
        if self.ylog:
            self.text.set_y(self.yoff*y)
        else:
            self.text.set_y(self.yoff+y)
        
    def drag_end(self,event):
        print("drag end")
        self.ax.figure.canvas.mpl_disconnect(self.drag['cid'])
        xdata = self.line.get_xdata()
        ydata = self.line.get_ydata()
        
        if self.xlog:
            xdata *= event.xdata / self.drag['x']
        else:
            xdata += (event.xdata - self.drag['x'])
        if self.ylog:
            ydata *= event.ydata / self.drag['y']
        else:
            ydata += event.ydata - self.drag['y']
        self.line.set_xdata(xdata)
        self.line.set_ydata(ydata)
        self.update_text_pos()
        event.canvas.draw()


def function_contours(f=lambda x,y: x-y,ax=None,Nx=20,Ny=20,V=10,
                      fmt=None):
    """ Cheap way to draw contours of a function and label them.
    Just evaluates the function on a grid and calls contour
    """
    ax = ax or pl.gca()
    xxyy = ax.axis()
    x = np.linspace(xxyy[0],xxyy[1],Nx)
    y = np.linspace(xxyy[2],xxyy[3],Ny)
    X,Y = np.meshgrid(x,y)
    Z = f(X,Y)
    ctr = pl.contour(X,Y,Z,V,colors='k')
    if fmt:
        ax.clabel(ctr,fmt=fmt)
        
    return ctr


def bode(G,f=np.arange(.01,100,.01),fig=None):
    fig = fig or plt.figure()
    jw = 2*np.pi*f*1j
    y = np.polyval(G.num, jw) / np.polyval(G.den, jw)
    mag = 20.0*np.log10(abs(y))
    phase = np.arctan2(y.imag, y.real)*180.0/np.pi % 360

    plt.subplot(211)
    #plt.semilogx(jw.imag, mag)
    plt.semilogx(f,mag)
    plt.grid()
    plt.gca().xaxis.grid(True, which='minor')

    plt.ylabel(r'Magnitude (db)')

    plt.subplot(212)
    #plt.semilogx(jw.imag, phase)
    plt.semilogx(f,phase)
    plt.grid()
    plt.gca().xaxis.grid(True, which='minor')
    plt.ylabel(r'Phase (deg)')
    plt.yticks(np.arange(0, phase.min()-30, -30))

    return mag, phase


def annotate_line(l,s,norm_position=0.5,offset_points=10,ax=None,**kwargs):
    """
    line: a matplotlib line object
    s: string to show
    norm_position: where along the line, normalized to [0,1]
    offset_points: how to offset the text baseline relative to the line.
    """
    ax=ax or plt.gca()

    x,y = l.get_data()

    deltas = np.sqrt(np.diff(x)**2 + np.diff(y)**2)
    deltas = np.concatenate( ([0],deltas) )
    dists = np.cumsum(deltas)
    abs_position = norm_position*dists[-1]
    if norm_position < 0.99:
        abs_position2 = (norm_position+0.01)*dists[-1]
    else:
        abs_position2 = (norm_position-0.01)*dists[-1]

    x_of_label = np.interp(abs_position,dists,x)
    y_of_label = np.interp(abs_position,dists,y)
    dx = np.interp(abs_position2,dists,x) - x_of_label
    dy = np.interp(abs_position2,dists,y) - y_of_label
    angle = np.arctan2(dy,dx)*180/np.pi

    perp = np.array([-dy,dx])
    perp = offset_points * perp / utils.mag(perp)
    
    settings=dict(xytext=perp, textcoords='offset points',
                  rotation=angle,
                  ha='center',va='center')
    settings.update(kwargs)
    ax.annotate(s,[x_of_label,y_of_label],**settings)

def klabel(k,txt,color='0.5',ax=None,y=None,**kwargs):
    ax = ax or plt.gca()
    ax.axvline(k,color=color)
    args=dict(rotation=90,va='bottom',ha='right',
              color=color)
    args.update(kwargs)
    if y is None:
        y=0.02+0.6*np.random.random()
    return ax.text(k,y,txt,
                   transform=ax.get_xaxis_transform(),
                   **args)


class ScaleXOnly(Transform):
    """ Given a base transform, the x origin is preserved
    but x scaling is taken from a second transformation.
    An optional xoffset is applied to the origin.
    
    Useful for having a scalebar with one side in a consistent
    location in ax.transAxes coordinates, but the length of
    the bar adjusts with the data transformation.
    """
    is_separable=True
    input_dims = 2
    output_dims = 2
    pass_through=True # ?

    def __init__(self,origin,xscale,xoffset=None,**kwargs):
        Transform.__init__(self, **kwargs)
        self._origin=origin
        self._xscale=xscale or 0.0
        self._xoffset=xoffset

        assert(xscale.is_affine)
        assert(xscale.is_separable)
        self.set_children(origin,xscale)
        self._affine = None

    def __eq__(self, other):
        if isinstance(other, ScaleXOnly):
            return (self._origin == other._origin) and (self._xscale==other._xscale) and \
                (self._xoffset == other._xoffset)
        else:
            return NotImplemented
    def contains_branch_seperately(self, transform):
        x,y=self._origin.contains_branch_seperately(transform)
        xs,ys=self._xscale.contains_branch_seperately(transform)
        return (x or xs,y)
    @property
    def depth(self):
        return max([self._origin.depth,self._xscale.depth])

    def contains_branch(self, other): 
        # ??
        # a blended transform cannot possibly contain a branch from two different transforms.
        return False

    @property
    def is_affine(self):
        # scale is always affine
        return self._origin.is_affine 

    def frozen(self):
        return ScaleXOnly(self._origin.frozen(),self._xscale.frozen(),self._xoffset)

    def __repr__(self):
        return "ScaleXOnly(%s)" % (self._origin,self._xscale,self._xoffset)

    def transform_non_affine(self, points):
        if self._origin.is_affine:
            return points
        else:
            return self._origin.transform_non_affine(points)
    
    # skip inversion for now.
    def get_affine(self):
        # for testing, do nothing here.
        if self._invalid or self._affine is None:
            mtx = self._origin.get_affine().get_matrix()
            mtx_xs = self._xscale.get_affine().get_matrix()
            # 3x3
            # x transform is the first row
            mtx=mtx.copy()
            mtx[0,2] += mtx[0,0]*self._xoffset # x offset in the origin transform
            mtx[0,0]=mtx_xs[0,0] # overrides scaling of x
            
            self._affine = Affine2D(mtx)
            self._invalid = 0
        return self._affine

def right_align(axs):
    xmax=min( [ax.get_position().xmax for ax in axs] )
    for ax in axs:
        p=ax.get_position()
        p.p1[0]=xmax
        ax.set_position(p)

def cbar(*args,**kws):
    extras=kws.pop('extras',[])
    cbar=plt.colorbar(*args,**kws)
    cbar_interactive(cbar,extras=extras)
    return cbar

def cbar_interactive(cbar,extras=[]):
    """ click in the upper or lower end of the colorbar to
    adjust the respective limit.
    left click to increase, right click to decrease
    extras: additional mappables.  When the norm is changed,
      these will get set_norm(norm) called.

    returns the callback.
    There is the possibility of callbacks being garbage collected
    if a reference is not retained, so it is recommended to keep

    the callback will attempt to remove itself if the colorbar 
    artists disappear from the cax.
    """
    mappables=[cbar.mappable] + extras
    original_clim=[cbar.mappable.norm.vmin,cbar.mappable.norm.vmax]
    def mod_norm(rel_min=0,rel_max=0,reset=False):
        nrm=cbar.mappable.norm
        if reset:
            nrm.vmin,nrm.vmax = original_clim
        else:
            rang=nrm.vmax - nrm.vmin
            nrm.vmax += rel_max*rang
            nrm.vmin += rel_min*rang
        [m.set_norm(nrm) for m in mappables]
        plt.draw()

    cid=None
    def cb_u_cbar(event=None):
        if event is None or \
           (cbar.solids is not None and \
            cbar.solids not in cbar.ax.get_children()):
            # print "This cbar is no longer relevant.  Removing callback %s"%cid
            fig.canvas.mpl_disconnect(cid)
            return
            
        if event.inaxes is cbar.ax:
            if cbar.orientation=='vertical':
                coord=event.ydata
            else:
                coord=event.xdata

            if event.button==1:
                rel=0.1
            elif event.button==3:
                rel=-0.1
            if coord<0.4:
                mod_norm(rel_min=rel)
            elif coord>0.6:
                mod_norm(rel_max=rel)
            else:
                mod_norm(reset=True)
    fig=cbar.ax.figure
    cid=fig.canvas.mpl_connect('button_press_event',cb_u_cbar)
    return cb_u_cbar



def rgb_key(vel_scale,ax):
    # key for vel_rgb
    # syn_Mag,syn_Dir are for quad corners - 
    syn_mag=syn_dir=np.linspace(0,1,20)
    syn_Mag,syn_Dir=np.meshgrid(syn_mag,syn_dir)

    # syn_cMag, syn_cDir are for quad centers
    syn_cMag,syn_cDir=np.meshgrid( 0.5*(syn_mag[1:]+syn_mag[:-1]),
                                   0.5*(syn_dir[1:]+syn_dir[:-1]) )

    syn_u=vel_scale*syn_cMag*np.cos(syn_cDir*2*np.pi)
    syn_v=vel_scale*syn_cMag*np.sin(syn_cDir*2*np.pi)

    syn_rgb=vec_to_rgb(syn_u,syn_v,vel_scale) 

    # not sure why Y has to be negated..
    syn_X=syn_Mag*np.cos(syn_Dir*2*np.pi)
    syn_Y=syn_Mag*np.sin(syn_Dir*2*np.pi)

    ax.cla()

    rgb_ravel=syn_rgb.reshape( [-1,3] )
    rgba_ravel=rgb_ravel[ :, [0,1,2,2] ]
    rgba_ravel[:,3]=1.0

    coll=ax.pcolormesh( syn_X,syn_Y,syn_rgb[:,:,0],
                        facecolors=rgba_ravel)
    coll.set_array(None)

    coll.set_facecolors(rgba_ravel)
    ax.xaxis.set_visible(0)
    ax.yaxis.set_visible(0)
    ax.set_frame_on(0)
    ax.text(0.5,0.5,'max %g'%vel_scale,transform=ax.transAxes)
    ax.axis('equal')

def vec_to_rgb(U,V,scale):
    h=(np.arctan2(V,U)/(2*np.pi)) % 1.0
    s=(np.sqrt(U**2+V**2)/scale).clip(0,1)
    v=1.0*np.ones_like(h)

    bad=~(np.isfinite(U) & np.isfinite(V))
    h[bad]=0
    s[bad]=0
    v[bad]=0.5

    i = (h*6.0).astype(int)

    f = (h*6.0) - i
    p = v*(1.0 - s)
    q = v*(1.0 - s*f)
    t = v*(1.0 - s*(1.0-f))

    r = i.choose( v, q, p, p, t, v, 0.5 )
    g = i.choose( t, v, v, q, p, p, 0.5 )
    b = i.choose( p, p, t, v, v, q, 0.5 )

    # not portable to other shapes...
    rgb = np.asarray([r,g,b]).transpose(1,2,0)
    
    return rgb


# def multi_plot(*args,**kwargs):

def savefig_geo(fig,fn,*args,**kws):
    # Not really tested...
    # Add annotations for the frontal zones:
    from PIL import Image

    fig.savefig(fn) # *args,**kws)
    # get the image resolution:
    img_size=Image.open(fn).size 

    w_fn=fn+'w'

    xxyy=fig.axes[0].axis()
    xpix=(xxyy[1] - xxyy[0]) / img_size[0]
    ypix=(xxyy[3] - xxyy[2]) / img_size[1]

    with open(w_fn,'wt') as fp:
        for v in [xpix,0,0,-ypix,xxyy[0],xxyy[3]]:
            fp.write("%f\n"%v)


# Transect methods:
def transect_tricontourf(data,xcoord,ycoord,V=None,
                         elide_missing_columns=True,sortx=True,
                         **kwargs):
    ax=kwargs.pop('ax',None)
    if ax is None:
        ax=plt.gca()
        
    tri,mapper = transect_to_triangles(data,xcoord,ycoord,
                                       elide_missing_columns=elide_missing_columns,
                                       sortx=sortx)
    if tri is None:
        return None
    
    if V is not None:
        args=[V]
    else:
        args=[]
    return ax.tricontourf(tri,mapper(data.values),*args,**kwargs)
    
def transect_to_triangles(data,xcoord,ycoord,
                          elide_missing_columns=True,
                          sortx=True):
    """
    data: xarray DataArray with two dimensions, first assumed to be
    horizontal, second vertical.
    xcoord,ycoord: each 1D or 2D, to be expanded as needed.
      Can be either the name of the respective coordinate in data,
      or an array to be used directly.
    elide_missing: if True, a first step drops columns (profiles) for
      which there is no valid data.  Otherwise, these columns will be
      shown as blanks.  Note that missing columns at the beginning or
      end are not affected by this
    sortx: force x coordinate to be sorted low to high.  
    return (triangulation,mapper)
    such that tricontourf(triangulation,mapper(data.values))
    generates a transect plot
    triangles are omitted based on entries in data being nan.
    """
    xdim,ydim=data.dims # assumption of the order!

    # conditional meshgrid, more or less.
    if isinstance(xcoord,string_types):
        X=data[xcoord].values
    else:
        X=xcoord
    if isinstance(ycoord,string_types):
        Y=data[ycoord].values
    else:
        Y=ycoord
        
    if X.ndim==1:
        X=X[:,None] * np.ones_like(data.values)
    if Y.ndim==1:
        Y=Y[None,:] * np.ones_like(data.values)

    # build up a triangulation and mapping for better display
    # assumed the triangles should be formed only between consecutive 

    triangles=[] # each triangle is defined by a triple of index pairs

    data_vals=data.values
    
    valid=np.isfinite(data_vals) # or consult mask

    xslice=np.arange(X.shape[0])
    if sortx:
        xslice=xslice[np.argsort(X[:,0])]
    
    if elide_missing_columns:
        valid_cols=np.any(valid[xslice,:],axis=1)
        xslice=xslice[valid_cols]

    # now xslice is an index array, in the right order, with
    # the right subset.
    X=X[xslice,:]
    Y=Y[xslice,:]
    data_vals=data_vals[xslice,:]
    valid=valid[xslice,:]

    for xi in range(data_vals.shape[0]-1):
        # initialize left_y and right_y to first valid datapoints
        for left_y in range(data_vals.shape[1]):
            if valid[xi,left_y]:
                break
        else:
            continue
        for right_y in range(data_vals.shape[1]):
            if valid[xi+1,right_y]:
                break
        else:
            continue
        
        for yi in range(1+min(left_y,right_y),data_vals.shape[1]):
            if (yi>left_y) and valid[xi,yi]:
                triangles.append( [[xi,left_y],[xi,yi],[xi+1,right_y]] )
                left_y=yi
            if valid[xi+1,yi]:
                triangles.append( [[xi,left_y],[xi+1,yi],[xi+1,right_y]] )
                right_y=yi
    if len(triangles)==0:
        return None,None # triangles=np.zeros((0,3),'i4')
    else:
        triangles=np.array(triangles)    

    nx=X.ravel()
    ny=Y.ravel()
    ntris=triangles[...,0]*X.shape[1] + triangles[...,1]
    tri=Triangulation(nx, ny, triangles=ntris)
    def trimap(data2d,xslice=xslice):
        rav=data2d[xslice,:].ravel().copy()
        # some tri functions like contourf don't deal well with
        # nan values.
        invalid=np.isnan(rav)
        rav[invalid]=-999
        rav=np.ma.array(rav,mask=invalid)
        return rav

    return tri,trimap


def inset_location(inset_ax,overview_ax):
    extents=inset_ax.axis()
    rect=Rectangle([extents[0],extents[2]],
                   width=extents[1] - extents[0],
                   height=extents[3] -extents[2],
                   lw=0.5,ec='k',fc='none')
    overview_ax.add_patch(rect)
    return rect




class RotatedPathCollection(collections.PathCollection):
    _factor = 1.0

    def __init__(self, paths, sizes=None, angles=None, **kwargs):
        """
        *paths* is a sequence of :class:`matplotlib.path.Path`
        instances.

        %(Collection)s
        """
        collections.PathCollection.__init__(self,paths,sizes,**kwargs)
        self.set_angles(angles)
        self.stale = True
    
    def set_angles(self, angles):
        if angles is None:
            self._angles = np.array([])
        else:
            self._angles = np.asarray(angles)
            orig_trans=self._transforms
            new_angles=self._angles

            if len(self._transforms)==1 and len(self._angles)==1:
                pass
            else:
                if len(self._transforms)==1:
                    orig_trans=[self._transforms] * len(self._angles)
                    new_angles=self._angles
                if len(self._angles)==1:
                    orig_trans=self.transforms
                    new_angles=[self._angles] * len(self._transforms)
                    
            self._transforms = [
                transforms.Affine2D(x).rotate(angle).get_matrix()
                for x,angle in zip(orig_trans,new_angles)
            ]

            self.stale = True

    def draw(self, renderer):
        self.set_sizes(self._sizes, self.figure.dpi)
        self.set_angles(self._angles)
        collections.Collection.draw(self, renderer)
        

def fat_quiver(X,Y,U,V,ax=None,**kwargs):
    U=np.asarray(U)
    V=np.asarray(V)
    mags=np.sqrt( (U**2 + V**2) )
    angles_rad=np.arctan2( V, U )
    
    ax=ax or plt.gca()
    # right facing fat arrow
    L=0.333
    Hw=0.1667
    Sw=0.0833
    Hl=0.1667

    pivot=kwargs.pop('pivot','tail')
    if pivot=='tip':
        dx=0
    elif pivot=='tail':
        dx=L+Hl
    elif pivot in ('middle','center'):
        dx=(L+Hl)/2.0

    marker =(path.Path(np.array( [ [dx + 0 ,0],
                                   [dx - Hl,-Hw],
                                   [dx - Hl,-Sw],
                                   [dx - Hl-L,-Sw],
                                   [dx - Hl-L,Sw],
                                   [dx - Hl,Sw],
                                   [dx - Hl,Hw],
                                   [dx + 0,0] ] ), None),)

    mags=np.sqrt( np.asarray(U)**2 + np.asarray(V)**2 )
    angles=np.arctan2(np.asarray(V),np.asarray(U))
    scale=kwargs.pop('scale',1)

    if 'color' in kwargs and 'facecolor' not in kwargs:
        # otherwise sets edges and faces
        kwargs['facecolor']=kwargs.pop('color')
    
    # sizes is interpreted as an area - i.e. the linear scale
    # is sqrt(size)
    coll=RotatedPathCollection(paths=marker,
                               offsets=np.array([X,Y]).T,
                               sizes=mags*50000/scale,
                               angles=angles,
                               transOffset=ax.transData,
                               **kwargs)
    trans = transforms.Affine2D().scale(ax.figure.dpi / 72.0)
    coll.set_transform(trans)  # the points to pixels transform

    ax.add_collection(coll)
    return coll
