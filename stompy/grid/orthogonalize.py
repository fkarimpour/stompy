"""
Prototyping some approaches for local orthogonalization
"""
from __future__ import print_function

import numpy as np

from stompy.grid import unstructured_grid

from stompy.utils import (mag, circumcenter, circular_pairs,signed_area, poly_circumcenter,
                          orient_intersection,array_append,within_2d, to_unit,
                          recarray_add_fields,recarray_del_fields)


# approach: adjust a single node relative to all of its
# surrounding cells, at first worrying only about orthogonality
# then start from a cell, and adjust each of its nodes w.r.t 
# to the nodes' neighbors.

class Tweaker(object):
    """
    Bundle optimization methods for unstructured grids.

    Separated from the grid representation itself, this class contains methods
    which act on the given grid.  
    """
    def __init__(self,g):
        self.g=g

    def nudge_node_orthogonal(self,n):
        g=self.g
        n_cells=g.node_to_cells(n)

        centers = g.cells_center(refresh=n_cells,mode='sequential')

        targets=[] # list of (x,y) which fit the individual cell circumcenters
        for n_cell in n_cells:
            cell_nodes=g.cell_to_nodes(n_cell)
            # could potentially skip n_cell==n, since we can move that one.
            if len(cell_nodes)<=3:
                continue # no orthogonality constraints from triangles at this point.

            offsets = g.nodes['x'][cell_nodes] - centers[n_cell,:]
            dists = mag(offsets)
            radius=np.mean(dists)

            # so for this cell, we would like n to be a distance of radius away
            # from centers[n_cell]
            n_unit=to_unit(g.nodes['x'][n]-centers[n_cell])

            good_xy=centers[n_cell] + n_unit*radius
            targets.append(good_xy)
        if len(targets):
            target=np.mean(targets,axis=0)
            g.modify_node(n,x=target)
            return True
        else:
            return False

    def nudge_cell_orthogonal(self,c):
        for n in self.g.cell_to_nodes(c):
            self.nudge_node_orthogonal(n)

    def calc_halo(self, node_idxs, max_halo=20):
        """
        calculate how many steps each node in node_idxs is away
        from a node *not* in node_idxs.
        max_halo: used to truncate the search and also as a default 
         value if there are no adjacent nodes not in node_idxs.
        """
        g=self.g
        # Come up with weights based on rings
        node_insets=np.zeros( len(node_idxs), np.int32) - 1

        # Outer ring:
        stack=[]
        for ni,n in enumerate(node_idxs):
            for nbr in g.node_to_nodes(n):
                if nbr not in node_idxs:
                    node_insets[ni]=0 # on the outer ring.
                    stack.append(ni)

        while stack:
            ni=stack.pop(0)
            n=node_idxs[ni]
            if node_insets[ni]>=max_halo: continue

            for nbr in g.node_to_nodes(n):
                nbri=np.nonzero(node_idxs==nbr)[0]
                if nbri.size==0: continue
                nbri=nbri[0]
                if node_insets[nbri]<0:
                    node_insets[nbri]=1+node_insets[ni]
                    stack.append(nbri)

        node_insets[node_insets<0]=max_halo
        
        return node_insets
            
    def local_smooth(self,node_idxs,ij=None,n_iter=3,stencil_radius=1,
                     free_nodes=None,min_halo=2):
        """
        Fit regular grid patches iteratively within the subset of nodes given
        by node_idxs.
        Currently requires that node_idxs has a sufficiently large footprint
        to have some extra nodes on the periphery.

        node_idxs: list of node indices
        n_iter: count of how many iterations of smoothing are applied.
        stencil_radius: controls size of the patch that is fit around each
        node.
        min_halo: only nodes at least this many steps from a non-selected node
        are moved.
        free_subset: node indexes (i.e. indices of g.nodes) that are allowed 
         to move.  Defaults to all of node_idxs subject to the halo.
        """
        g=self.g
        
        if ij is None:
            node_idxs,ij=g.select_quad_subset(ctr=None,max_cells=None,max_radius=None,node_set=node_idxs)

        halos=self.calc_halo(node_idxs)
            
        pad=1+stencil_radius
        ij=ij-ij.min(axis=0) + pad
        XY=np.nan*np.zeros( (pad+1+ij[:,0].max(),
                             pad+1+ij[:,1].max(),
                             2), np.float64)
        XY[ij[:,0],ij[:,1]]=g.nodes['x'][node_idxs]

        stencil_rows=[]
        for i in range(-stencil_radius,stencil_radius+1):
            for j in range(-stencil_radius,stencil_radius+1):
                stencil_rows.append([i,j])
        stencil=np.array(stencil_rows)

        # And fit a surface to the X and Y components
        #  Want to fit an equation
        #   x= a*i + b*j + c
        M=np.c_[stencil,np.ones(len(stencil))]
        new_XY=XY.copy()

        if free_nodes is not None:
            # use dict for faster tests
            free_nodes={n:True for n in free_nodes}
            
        moved_nodes={}
        for count in range(n_iter):
            new_XY[...]=XY
            for ni,n in enumerate(node_idxs):
                if halos[ni]<min_halo: continue
                if (free_nodes is not None) and (n not in free_nodes): continue

                # Cruft, pretty sure.
                # # Find that node in
                # ni=np.nonzero(node_idxs==n)[0]
                # assert len(ni)>0,"Somehow n wasn't in the quad subset"
                # ni=ni[0]

                # Query XY to estimate where n "should" be.
                i,j=ij[ni]

                XY_sten=(XY[stencil[:,0]+ij[ni,0],stencil[:,1]+ij[ni,1]]
                         -XY[i,j])
                valid=np.isfinite(XY_sten[:,0])

                xcoefs,resid,rank,sing=np.linalg.lstsq(M[valid],XY_sten[valid,0],rcond=-1)
                ycoefs,resid,rank,sing=np.linalg.lstsq(M[valid],XY_sten[valid,1],rcond=-1)

                delta=np.array( [xcoefs[2],
                                 ycoefs[2]])

                new_x=XY[i,j] + delta
                if np.isfinite(new_x[0]):
                    new_XY[i,j]=new_x
                    moved_nodes[n]=True
                else:
                    pass # print("Hit nans.")
            # Update all at once to avoid adding variance due to the order of nodes.
            XY[...]=new_XY

        # Update grid
        count=0
        for ni,n in enumerate(node_idxs):
            if n not in moved_nodes: continue
            i,j=ij[ni]
            dist=mag(XY[i,j] - g.nodes['x'][n])
            if dist>1e-6:
                g.modify_node(n,x=XY[i,j])
                count+=1

        for n in list(moved_nodes.keys()):
            for nbr in g.node_to_nodes(n):
                if nbr not in moved_nodes:
                    moved_nodes[nbr]=True
        for n in moved_nodes.keys():
            if (free_nodes is not None) and (n not in free_nodes): continue
            self.nudge_node_orthogonal(n)


# A conformal mapping approach to smoothing.
# May be useful in the future, but as it is now it is too sensitive
# and restrictive.  It tries to fit a simple mapping to a large group
# of nodes.  The mapping is too simple, and ends up going through some
# contortions to minimize the error.  Might be more useful when applied
# in a more local context.


            
#   def fwd_transform(vec,Z,X0,error_weights):
#       """
#       The Z=complex ij => real X transform.
#       vec: parameters for the transform:
#          aspect: how much narrow cells are in the j dimension than i dimension
#          inv_center_i/j: the inverse of the center of curvature in the complex ij plane.
#            or 0,0 for no curvature
#         scale: isotropic scaling
#         tele_i,j: telescoping factors in i,j directions
#       """
#       # the parameters being optimized
#       # Optimize over inverse center to avoid singularity with zero curvature
#       aspect,inv_center_i,inv_center_j,scale,theta,tele_i,tele_j = vec
#       inv_eps=0.0001
#   
#       Ztran=Z
#   
#       y=np.imag(Ztran)
#       if np.abs(tele_j)>1e-4:
#           y=(np.exp(tele_j*y)-1)/tele_j
#       y=y*aspect
#       x=np.real(Ztran)
#       if np.abs(tele_i)>1e-4:
#           x=(np.exp(tele_i*x)-1)/tele_i
#   
#       Ztran=x + 1j*y
#   
#       # Curvature can be done with a single
#       # center, complex valued.  But for optimization, use the
#       # inverse, and flip around here.
#       inv_center=inv_center_i + 1j*inv_center_j
#       if np.abs(inv_center) > inv_eps:
#           center=1./inv_center
#           Ztran=np.exp(Ztran/center)*center
#   
#       Ztran=scale*Ztran
#   
#       Ztran=Ztran*np.exp(1j*theta)
#   
#       # move back to R2 plane
#       Xz=np.c_[ np.real(Ztran), np.imag(Ztran)]
#       
#       # make the offset match where we can't move nodes
#       offset=((Xz-X0)*error_weights[:,None]).sum(axis=0) / error_weights.sum()
#       Xz-=offset
#   
#       return Xz
#   
#   def conformal_smooth(g,ctr,max_cells=250,max_radius=None,halo=[0,5],max_weight=1.0):
#       node_idxs,ij=g.select_quad_subset(ctr,max_cells=max_cells,max_radius=max_radius)
#   
#       # node coordinates in complex grid space
#       Z=(ij - ij.mean(axis=0)).dot( np.array([1,1j]) )
#   
#       # node coordinates in real space.
#       X=g.nodes['x'][node_idxs]
#       Xoff=X.mean(axis=0)
#       X0=X-Xoff
#   
#       halos=calc_halo(g,node_idxs)
#   
#       # how much a node will be updated
#       # This leaves the outer two rings in place, partially updates
#       # the next ring, and fully updates anybody inside of there
#       update_weights=np.interp(halos, halo,[0,1])
#       error_weights=1-update_weights
#       update_weights *= max_weight
#   
#       def cost(vec):
#           Xtran=fwd_transform(vec,Z,X0,error_weights)
#           err=  (((Xtran-X0)**2).sum(axis=1)*error_weights).sum() / error_weights.sum()
#           return err
#   
#       vec_init=[1.0,0.001,0.001,5,1.0,0.0,0.0]
#       best=fmin(cost,vec_init)
#   
#       fit=fwd_transform(best,Z,X0,error_weights) + Xoff
#   
#       new_node_x=( (1-update_weights)[:,None]*g.nodes['x'][node_idxs]
#                    + update_weights[:,None]*fit )
#       # May provide some other options here.  This is the safest and simplest
#       # update route, but probably slow.
#       for ni,n in enumerate(node_idxs):
#           if update_weights[ni]>0.0:
#               g.modify_node(n,x=new_node_x[ni])
#       return node_idxs
            
