"""
Augment DFM/DWAQ output so that it can be used as hydro input
for FISH-PTM.

in FISH_PTM.inp, set subgrid bathy to false.

Requirements on the run:
  DFM and DWAQ output must be synchronized, with the same start/stop/interval
  settings.  In most cases this just means that MapInterval and WaqInterval
  have the same value in the MDU file.

MapFormat: in theory this can be 1,3 or 4, meaning old-style netcdf (1,3) or
  UGRID-ish netcdf (4).  Experience with subversion dflowfm rev 52184 and 53925
  shows a bug when combining MPI, DWAQ output, and UGRID.

  To get to a working setup as quickly as possible, development is focusing on
  converting single-core UGRID w/ DWAQ output.


Variables required by PTM at each output interval include (those listed
in get_netcdf_hydro_record):
  h_flow_avg
  v_flow_avg
  Mesh2_edge_wet_area
  Mesh2_face_wet_area
  Mesh2_face_water_volume
  Mesh2_salinity_3d
  Mesh2_vertical_diffusivity_3D
  Mesh2_sea_surface_elevation
  Mesh2_edge_bottom_layer
  Mesh2_edge_top_layer
  Mesh2_face_bottom_layer
  Mesh2_face_bottom_layer

An example metadata description:
double h_flow_avg(nMesh2_edge=76593, nMesh2_layer_3d=54, nMesh2_data_time=483);
  :standard_name = "ocean_volume_transport_across_line";
  :long_name = "horizontal volume flux average over integration interval";
  :coordinates = "Mesh2_edge_x Mesh2_edge_y Mesh2_edge_lon Mesh2_edge_lat Mesh2_edge_z_3d";
  :mesh = "Mesh2";
  :grid_mapping = "Mesh2_crs";
  :location = "edge";
  :units = "m3 s-1";
  :_ChunkSizes = 11949, 18, 1; // int

This is the average volume flux at an edge (each j,k) over the preceeding time interval.
"""
##
import sys
import six
import os
import glob
import netCDF4
import numpy as np
import xarray as xr

try:
    profile
except NameError:
    def profile(x):
        return x

from stompy import utils
import stompy.model.delft.io as dio
from stompy.model.delft import dfm_grid
from stompy.grid import unstructured_grid
import stompy.model.delft.waq_scenario as waq

class DFlowToPTMHydro(object):
    overwrite=False
    time_slice=slice(None)

    write_grd=False
    grd_fn=None

    write_nc=True

    def __init__(self,mdu_path,output_fn,**kwargs):
        self.__dict__.update(kwargs)

        self.mdu_path=mdu_path
        self.output_fn=output_fn

        self.mdu=dio.MDUFile(mdu_path)

        # check the naming of DFM output files
        dfm_out_dir=self.mdu.output_dir()

        map_file_serial=os.path.join( dfm_out_dir,
                                      self.mdu.name+"_map.nc")
        if os.path.exists(map_file_serial):
            self.nprocs=1
            self.map_file=map_file_serial
        else:
            raise Exception("Not ready for MPI runs")

        self.open_dflow_output()

        if self.write_grd:
            self.write_grd(self.grd_fn)

        if self.write_nc:
            self.open_waq_output()
            self.initialize_output()
            try:
                self.initialize_output_variables()
                self.write_time_steps()
            finally:
                # helps netCDF4 release the dataset and not block
                # subsequent runs in the case of an error on this
                # run.
                self.close()

    def open_dflow_output(self):
        """
        open dfm netcdf output as (1) original (2) with renames,
        and (3) as unstructured_grid
        """
        # incoming dataset from DFM:
        self.map_ds=xr.open_dataset(self.map_file)
        # Additionally trim to subset of times here:
        subset_ds=self.map_ds.isel(time=self.time_slice)

        # shallow copy of that with renames for PTM compatibility
        self.mod_map_ds=subset_ds.rename({'time':'nMesh2_data_time',
                                          'nmesh2d_face':'nMesh2_face',
                                          'nmesh2d_edge':'nMesh2_edge',
                                          'nmesh2d_node':'nMesh2_node',
                                          'max_nmesh2d_face_nodes':'nMaxMesh2_face_nodes',
                                          'mesh2d_face_x':'Mesh2_face_x',
                                          'mesh2d_face_y':'Mesh2_face_y',
                                          'mesh2d_edge_x':'Mesh2_edge_x',
                                          'mesh2d_edge_y':'Mesh2_edge_y'
        })

        self.g=unstructured_grid.UnstructuredGrid.from_ugrid(self.map_ds)
        # copy depth into a field where it is expected by the code that
        # writes a ptm grid.  note this is a positive:up quantity
        self.g.add_cell_field('depth',self.g.cells['mesh2d_flowelem_bl'])

        # set markers as ptm expects:
        # 0: internal, 1 external, 2 flow, 3 open
        # from DFM: 0=> internal closed, 1=>internal, 2=>flow or stage bc, 3=>closed
        # map to -1 (error), 0=>internal, 1=>closed, 2=>flow.  no easy way to
        # distinguish flow from stage bc right here.
        translator=np.array([-1,0,2,1])
        self.g.edges['mark'][:]=translator[ self.map_ds.mesh2d_edge_type.values.astype(np.int32) ]

        self.g.cells['mark'][:]=0
        # punt, and call any cell adjacent to a marked edge BC a stage-bc cell
        bc_edges=np.nonzero(self.g.edges['mark']>1)[0]
        bc_cells=self.g.edge_to_cells(bc_edges).max(axis=1) # drop the negative neighbors
        self.g.cells['mark'][bc_cells]=1

        # regardless of the how DFM was configured, we will set edge
        # depths to the shallower of the cells
        e2c=self.g.edge_to_cells()
        n1=e2c[:,0] ; n2=e2c[:,1]

        # but no info right here on flow/open boundaries.
        n1=np.where(n1>=0,n1,n2)
        n2=np.where(n2>=0,n2,n1)
        edge_depths=np.maximum( self.g.cells['depth'][n1],
                                self.g.cells['depth'][n2] )
        self.g.add_edge_field('depth',edge_depths)

        # flip edges to keep invariant that external cells are always
        # second.
        e2c=self.g.edge_to_cells()
        to_flip=e2c[:,0]<0
        for fld in ['nodes','cells']:
            a=self.g.edges[fld][to_flip][:,0].copy()
            b=self.g.edges[fld][to_flip][:,1].copy()
            self.g.edges[fld][to_flip,0] = b
            self.g.edges[fld][to_flip,1] = a

        self.flipped=to_flip

    def write_grd(self,grd_fn):
        self.g.write_ptm_gridfile(grd_fn,overwrite=self.overwrite,
                                  subgrid=True)

    def template_ds(self):
        """
        Construct an xarray dataset with static geometry and basic
        dimensions.
        """

        out_ds=self.g.write_to_xarray(mesh_name="Mesh2",
                                      node_coordinates="Mesh2_node_x Mesh2_node_y",
                                      face_node_connectivity='Mesh2_face_nodes',
                                      edge_node_connectivity='Mesh2_edge_nodes',
                                      face_dimension='nMesh2_face',
                                      edge_dimension='nMesh2_edge',
                                      node_dimension='nMesh2_node')
        out_ds=out_ds.rename({
            'maxnode_per_face':'nMaxMesh2_face_nodes',
            'node_per_edge':'Two'
        })

        # Additional grid information:
        # xarray wants the dimension made explicit here -- don't know why.
        out_ds['Mesh2_face_x']=('nMesh2_face',),self.mod_map_ds['Mesh2_face_x']
        out_ds['Mesh2_face_y']=('nMesh2_face',),self.mod_map_ds['Mesh2_face_y']

        out_ds['Mesh2_edge_x']=('nMesh2_edge',),self.mod_map_ds['Mesh2_edge_x']
        out_ds['Mesh2_edge_y']=('nMesh2_edge',),self.mod_map_ds['Mesh2_edge_y']

        e2c=self.g.edge_to_cells()
        out_ds['Mesh2_edge_faces']=('nMesh2_edge','Two'),e2c

        face_edges=np.array([self.g.cell_to_edges(c,pad=True)
                             for c in range(self.g.Ncells())] )

        out_ds['Mesh2_face_edges']=('nMesh2_face','nMaxMesh2_face_nodes'),face_edges
        out_ds['Mesh2_face_depth']=('nMesh2_face',),-self.mod_map_ds['mesh2d_flowelem_bl'].values
        out_ds['Mesh2_face_depth'].attrs.update({'positive':'down',
                                                 'unit':'m',
                                                 'standard_name':'sea_floor_depth_below_geoid',
                                                 'mesh':'Mesh2',
                                                 'long_name':'Mean elevation of bed in face'})

        # recreate edge bed level based on a constant bedlevtype
        bedlevtype=int(self.mdu['geometry','BedLevType'])
        if bedlevtype==3:
            edge_z=self.map_ds.mesh2d_node_z.values[self.g.edges['nodes']].mean(axis=1)
        elif bedlevtype==4:
            edge_z=self.map_ds.mesh2d_node_z.values[self.g.edges['nodes']].min(axis=1)
        else:
            raise Exception("Only know how to deal with bed level type 3,4 not %d"%bedlevtype)
        # mindful of positive-down sign convention needed by PTM
        out_ds['Mesh2_edge_depth']=('nMesh2_edge',),-edge_z
        out_ds['Mesh2_edge_depth'].attrs.update({'positive':'down',
                                                 'unit':'m',
                                                 'standard_name':'sea_floor_depth_below_geoid',
                                                 'mesh':'Mesh2',
                                                 'long_name':'Mean elevation of bed on edge'})

        out_ds['Mesh2_data_time']=self.mod_map_ds.nMesh2_data_time

        if 1:
            # This may not be necessary -- this keeps the freesurface
            # from appearing below the bed in cells, but these should
            # appear as dry based on ktop/kbot.
            # also, writing anything time-varying beyond the time stamps themselves
            # should probably be handled in the time loop [TODO]
            s1=np.maximum( self.mod_map_ds.mesh2d_s1, -out_ds['Mesh2_face_depth'])
            out_ds['Mesh2_sea_surface_elevation']=('nMesh2_face','nMesh2_data_time'),s1.T

        if 1: # edge and cell marks
            edge_marks=self.g.edges['mark']
            assert not np.any(edge_marks<0),"Need to implement internal closed edges"
            # this gets us to 0: internal, 1:boundary, 2: boundary_closed
            # this looks like 1 for stage or flow BC, 2 for land, 0 for internal.
            out_ds['Mesh2_edge_bc']=('nMesh2_edge',),edge_marks

            # 'facemark':'Mesh2_face_bc'
            out_ds['Mesh2_face_bc']=('nMesh2_face',),self.g.cells['mark']

        if 1: # layers
            ucx=self.mod_map_ds['mesh2d_ucx']
            if ucx.ndim==2:
                self.nkmax=1
                self.map_2d=True
            else:
                self.nkmax=ucx.shape[-1] # is it safe to assume nkmax is last in DFM?
                self.map_2d=False
            out_ds['nMesh2_layer_3d']=('nMesh2_layer_3d',),np.arange(self.nkmax)

            # based on sample output, the last of these is not used,
            # so this would be interfaces, starting with the top of the lowest layer.
            # fabricate something in sigma coordinates for now.
            sigma_layers=np.linspace(-1,0,self.nkmax+1)[1:]
            out_ds['Mesh2_layer_3d']=('nMesh2_layer_3d',),sigma_layers
            attrs=dict(standard_name="ocean_sigma_coordinate",
                       dz_min=0.001, # not real, but ptm tries to read this.
                       long_name="sigma layer coordinate at flow element top",
                       units="",
                       positive="up", # kind of baked into the sigma definition
                       formula_terms="sigma: Mesh2_layer_3d eta: Mesh2_sea_surface_elevation bedlevel: Mesh2_face_depth"
            )
            out_ds['Mesh2_layer_3d'].attrs.update(attrs)

        # this would be for adding more scalars to be extracted at particle positions
        # Just guessing with 1 -- maybe 0 is more appropriate?
        out_ds['nsp']=('nsp',),np.arange(1)

        # from http://cfconventions.org/Data/cf-conventions/cf-conventions-1.0/build/apd.html
        #    z(n,k,j,i) = eta(n,j,i) + sigma(k)*(depth(j,i)+eta(n,j,i))
        # sigma coordinate definition has z=positive:up baked in, likewise depth is
        # positive down, and eta positive up, with sigma ranging from -1 (bed) to 0 (surface)

        # for writing the output, use xarray to initialize the file, but
        # the big data part is best handled directly by netCDF4 so we can
        # control how much data is in RAM at a time.
        return out_ds

    def initialize_output(self):
        base_ds=self.template_ds()
        if os.path.exists(self.output_fn):
            if self.overwrite:
                os.unlink(self.output_fn)
        # maybe not strictly necessary, but might be more
        # scalable or flexible in the future
        base_ds.encoding['unlimited_dims']=['nMesh2_data_time']
        base_ds.to_netcdf(self.output_fn)

        # and re-open as direct netCDF4 for heavy writing
        self.out_nc=netCDF4.Dataset(self.output_fn,mode="a")

    def initialize_output_variables(self):
        """ Add the time-varying variables to the netcdf output.
        """
        # PTM expects time last
        self.cell_3d_data_dims=('nMesh2_face','nMesh2_layer_3d','nMesh2_data_time')
        self.edge_3d_data_dims=('nMesh2_edge','nMesh2_layer_3d','nMesh2_data_time')
        self.cell_2d_data_dims=('nMesh2_face','nMesh2_data_time')
        self.edge_2d_data_dims=('nMesh2_edge','nMesh2_data_time')

        # Scalar-ish variables
        if 'mesh2d_sa1' in self.mod_map_ds:
            self.salt_var=self.out_nc.createVariable('Mesh2_salinity_3d',
                                                     np.float64, self.cell_3d_data_dims)
        else:
            self.salt_var=None

        self.nut_var=self.out_nc.createVariable('Mesh2_vertical_diffusivity_3d',
                                                np.float64, self.cell_3d_data_dims)

        # Layer index variables
        self.edge_k_bot_var=self.out_nc.createVariable('Mesh2_edge_bottom_layer',
                                                       np.int32,
                                                       self.edge_2d_data_dims)
        self.edge_k_top_var=self.out_nc.createVariable('Mesh2_edge_top_layer',
                                                       np.int32,
                                                       self.edge_2d_data_dims)
        self.cell_k_bot_var=self.out_nc.createVariable('Mesh2_face_bottom_layer',
                                                       np.int32,
                                                       self.cell_2d_data_dims)
        self.cell_k_top_var=self.out_nc.createVariable('Mesh2_face_top_layer',
                                                       np.int32,
                                                       self.cell_2d_data_dims)

        # hydro variables
        self.h_flow_var=self.out_nc.createVariable('h_flow_avg',np.float64,self.edge_3d_data_dims)
        # what are the expectations for surface/bed vertical velocity?
        self.v_flow_var=self.out_nc.createVariable('v_flow_avg',np.float64,self.cell_3d_data_dims)

        self.vol_var=self.out_nc.createVariable('Mesh2_face_water_volume',np.float64,self.cell_3d_data_dims)
        self.A_edge_var=self.out_nc.createVariable('Mesh2_edge_wet_area',np.float64,self.edge_3d_data_dims)
        self.A_face_var=self.out_nc.createVariable('Mesh2_face_wet_area',np.float64,self.cell_3d_data_dims)

    def write_time_strings(self):

        # special handling for character array which xarray botches
        time_strings=[ utils.to_datetime(t).strftime('%Y-%m-%d %H:%M:%S')
                       for t in self.mod_map_ds.nMesh2_data_time.values ]
        # fish ptm expects this to be a 2D array, with string length
        # first, followed by time index.
        time_string_array=np.array( [ np.frombuffer( t.encode(),dtype='S1' )
                                      for t in time_strings ] )
        self.out_nc.createDimension('date_string_length',time_string_array.shape[1])
        time_string_var=self.out_nc.createVariable('Mesh2_data_time_string','c',
                                                   ('date_string_length','nMesh2_data_time'))
        time_string_var[:]=time_string_array.T

    def open_waq_output(self):
        self.hyd_fn=os.path.join(self.mdu.base_path,
                                 "DFM_DELWAQ_%s"%self.mdu.name,
                                 "%s.hyd"%self.mdu.name)
        self.hyd=waq.HydroFiles(self.hyd_fn)

        self.hyd.infer_2d_links()
        self.poi0=self.hyd.pointers-1
        self.init_waq_mappings()

    def init_waq_mappings(self):
        """
        establish mapping from hydro links to grid edges.
        sets
         self.link_to_edge_sign: [ (j from grid, +-1 to indicate flipped), ...]
          (indexed by waq link indexes)

        """

        # link_to_edge_sign=[] # an edge index in g.edges, and a +-1 sign for whether the link is aligned the same.
        # use array to allow for vector operations later
        link_to_edge_sign=np.zeros( (len(self.hyd.links),2), np.int32)
        link_to_edge_sign[:,0]=-1 # no edge
        link_to_edge_sign[:,0]=0  # 0 sign

        mapped_edges={} # make sure we don't map multiple links onto the same edge

        for link_idx,(l_from,l_to) in enumerate(self.hyd.links):
            if l_from>=0 and l_to>=0:
                j=self.g.cells_to_edge(l_from,l_to)
                j_cells=self.g.edge_to_cells(j)
                if j_cells[0]==l_from and j_cells[1]==l_to:
                    sign=1
                elif j_cells[1]==l_from and j_cells[0]==l_to:
                    sign=-1
                else:
                    assert False,"We have lost our way"
                link_to_edge_sign[link_idx,:]=[j,sign]
                assert j not in mapped_edges
                mapped_edges[j]=link_idx
            else:
                assert l_to>=0,"Was only expecting 'from' for the link to be negative"
                nbr_cells=np.array(self.g.cell_to_cells(l_to))
                nbr_edges=np.array(self.g.cell_to_edges(l_to))
                potential_edges=nbr_edges[nbr_cells<0]
                if len(potential_edges)==1:
                    j=potential_edges[0]
                elif len(potential_edges)==0:
                    print("No boundary edge for link %d->%d to an edge"%(l_from,l_to))
                    link_to_edge_sign[link_idx,:]=[9999999,0] # may be able to relax this
                    continue
                else:
                    print("Link %d->%d could map to %d edges - will choose first unclaimed"
                          %(l_from,l_to,len(potential_edges)))
                    # may not have enough information to know which boundary
                    for j in potential_edges:
                        if j in mapped_edges:
                            continue
                        break
                    else:
                        raise Exception("Couldn't find an edge for link %d->%d"%(l_from,l_to))
                mapped_edges[j]=link_idx
                j_cells=self.g.edge_to_cells(j)
                if j_cells[0]==l_to:
                    link_to_edge_sign[link_idx,:]=[j,-1]
                elif j_cells[1]==l_to:
                    link_to_edge_sign[link_idx,:]=[j,1]
                else:
                    assert False,"whoa there"

        self.link_to_edge_sign=link_to_edge_sign

    @profile
    def write_time_steps(self):
        """
        The heavy lifting writing out hydro fields at each time step.
        """
        times=self.mod_map_ds.nMesh2_data_time.values
        e2c=self.g.edge_to_cells()
        # when possible use the DWAQ areas, but for 2D, will use this
        # area since there isn't a dwaq cell area.
        Ac=self.g.cells_area()

        # this writes all time strings at once -- maybe that keeps those
        # small data contiguous for fast scanning.  Calling it from this
        # method maybe consolidates time step selection locations.
        self.write_time_strings()

        # "safe" versions of the cells on either side of an edge
        c1=e2c[:,0].copy() ; c2=e2c[:,1].copy()
        c2[c2<0]=c1[c2<0]
        c1[c1<0]=c2[c1<0] # unnecessary, but hey..

        for ti,t in enumerate(times):
            if True: # ti%24==0:
                print("%d/%d t=%s"%(ti,len(times),t))

            cell_water_depth=self.mod_map_ds.mesh2d_waterdepth.isel(nMesh2_data_time=ti)
            if 0:
                # try setting edges to be dry by k_top=0.  this is specific to nk=1
                # all or nothing for sigma layers
                self.cell_k_top_var[:,ti] = np.where(cell_water_depth>0,self.nkmax,0)
            else:
                # based on looking at untrim output, seems that cells are *not*
                # dried out by setting cell_top=0, though they do show a zero wet area.
                self.cell_k_top_var[:,ti] = self.nkmax

            # edge eta is taken from the higher freesurface
            eta_cell=self.out_nc['Mesh2_sea_surface_elevation'][:,ti]
            edge_eta=np.maximum( eta_cell[c1], eta_cell[c2] )
            edge_water_depth=edge_eta + self.out_nc['Mesh2_edge_depth'][:]
            # all or nothing for sigma layers
            self.edge_k_top_var[:,ti] = np.where(edge_water_depth>0,self.nkmax,0)

            # bed never moves in this code
            self.cell_k_bot_var[:,ti] = 1
            self.edge_k_bot_var[:,ti] = 1

            def copy_3d_cell(src,dst):
                # Copies single time step of cell-centered 3D data.
                # src: string name of variable in mod_map_ds
                # dst: netCDF variable to assign to.
                src_data=self.mod_map_ds[src].isel(nMesh2_data_time=ti).values
                if self.map_2d:
                    dst[:,0,ti]=src_data
                else:
                    dst[:,:,ti]=src_data

            if self.salt_var is not None:
                copy_3d_cell('mesh2d_sa1',self.salt_var)
            if self.nkmax>1:
                copy_3d_cell('mesh2d_viw',self.nut_var)
            else:
                # punt - would be nice to calculate something based on
                # velocity, roughness, etc.
                self.nut_var[:,:,ti]=0.0

            # h_flow gets interesting as we have to read dwaq output
            # dwaq uses seconds from reference time
            hyd_t_sec=(t-utils.to_dt64(self.hyd.time0))/np.timedelta64(1,'s')
            # flows is all horizontal flows, layer by layer, surface to bed,
            # and then vertical flows.
            # only flow edges get flows, though.
            flows=self.hyd.flows(hyd_t_sec)
            areas=self.hyd.areas(hyd_t_sec)

            # compose exch_to_2d_link,link_to_edge_sign, weed out unmapped
            # links, and copy into h_flow_avg.  start with naive loops
            h_flow_avg=np.zeros((self.g.Nedges(),self.nkmax),np.float64)
            h_area_avg=np.zeros_like(h_flow_avg)

            # vectorized
            # just the horizontal exchanges
            exchs=np.arange(self.hyd.n_exch_x+self.hyd.n_exch_y)

            Qs=flows[exchs]
            # for horizontal exchanges in a sigma grid, this is a safe way
            # to get layer:
            ks=self.hyd.seg_k[self.poi0[exchs][:,1]]
            links=self.hyd.exch_to_2d_link['link'][exchs]

            link_sgns=self.hyd.exch_to_2d_link['sgn'][exchs]
            js_j_sgns=self.link_to_edge_sign[links,:]
            js=js_j_sgns[:,0]
            j_sgns=js_j_sgns[:,1]

            sgns=np.where(js>=0,link_sgns*j_sgns,0)

            # so far this is k in the DWAQ world, surface to bed.
            # but now we assign in the untrim sense, bed to surface.
            ptm_ks=self.nkmax-ks-1

            h_flow_avg[js,ptm_ks]=Qs*sgns
            h_area_avg[js,ptm_ks]=np.where(js>=0,areas[exchs],0.0)

            self.h_flow_var[:,:,ti]=h_flow_avg
            self.A_edge_var[:,:,ti]=h_area_avg

            v_flow_avg=np.zeros((self.g.Ncells(),self.nkmax), np.float64)
            v_area_avg=np.zeros_like(v_flow_avg)

            if self.nkmax>1:
                # this is here for future reference, but most of the
                # other code is not ready for 3D, and this code has not been
                # tested.
                for exch in range(self.hyd.n_exch_x+self.hyd.n_exch_y,self.hyd.n_exch):
                    # negate, because dwaq records this relative to the exchange,
                    # which is top-segment to next segment down.
                    Q=-flows[exch]
                    assert self.poi0[exch][0] >=0,"Wasn't expecting BC exchanges in the vertical"
                    seg_up,seg_down=self.poi0[exch][0,:2]
                    k_upper=self.hyd.seg_k[seg_up]
                    k_lower=self.hyd.seg_k[seg_down]
                    elt=self.hyd.seg_to_2d_element[seg_up]
                    assert k_upper+1==k_lower,"Thought this was a given"
                    assert elt==self.hyd.seg_to_2d_element[seg_down],"Maybe this wasn't a vertical exchange"
                    # based on looking at the untrim output, this should be recorded to
                    # the k of the lower layer, but also flipped to be bed->surface
                    # ordered
                    # assumes that dwaq cells are numbered the same as dfm cells.
                    v_flow_avg[elt,nkmax-k_lower-1]=Q
                    if k_upper==0: # repeat top flux
                        v_flow_avg[elt,nkmax-k_upper-1]=Q
            else:
                # At least populate the area, though it may not make a difference
                v_area_avg[:,0] = np.where(cell_water_depth>0,Ac,0.0)
            self.v_flow_var[:,:,ti]=v_flow_avg
            self.A_face_var[:,:,ti]=v_area_avg

            #   Mesh2_face_water_volume
            vols=self.hyd.volumes(hyd_t_sec)
            # assume again that cells are numbered the same.
            # they come to us ordered by first all the top layer, then the second
            # layer, on down to the bed.  convert to 3D, and reorder the layers
            vols=vols.reshape( (self.nkmax,self.g.Ncells()) )[::-1,:]
            self.vol_var[:,:,ti] = vols.T
    def close(self):
        self.out_nc.close()
        self.out_nc=None

# for vertical flows, there are nkmax layers, but nkmax-1
# internal flux faces, or nkmax+1 total faces.  how is the
# staggering expected to be handled? best guess:
#  v_flow_avg[ k=10 ] is the volume flux between volume[k=10]
# and volume[k=11], i.e. transport with the volume above
# this one.  it looks like, at least in the untrim output, that
# the last flux is repeated.  one confusing point is that in the
# case of a dry surface layer, we'd expect to see something
# like [Qa, Qb, Qc, Qc, 0], but instead I've seen
# [Qa, Qb, Qc, Qd, Qd].  I don't understand what that's about.
# look at cell 18, around time index 200, 201

if 1:
    # Testing
    mdu_path="/home/rusty/src/csc/dflowfm/runs/20180807_grid98_17/flowfm.mdu"
    converter=DFlowToPTMHydro(mdu_path,'test_hydro.nc',time_slice=slice(0,2),
                              grd_fn='test_sub.grd',overwrite=True)
elif __name__=='__main__':
    # Command line use:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mdu",help="MDU filename, e.g. 'my_run/flowfm.mdu'")
    parser.add_argument("output",help="Output filename, e.g. 'hydro.nc'" )
    parser.add_argument("--times",help="Time indexes, e.g. 0:10, 5")
    parser.add_argument("--subgrid","-s",help="Write fake subgrid output_sub.grd too",
                        action='store_true')
    parser.add_argument("--skip-nc","-n",help="Do not write netcdf, usu. in conjunction with --subgrid",
                        action='store_true')
    args=parser.parse_args()

    kwargs={}
    if args.times is not None:
        # parsing python slice syntax
        parts=[int(p) if p else None
               for p in args.times.split(':')]
        kwargs['time_slice']=slice(*parts)
    if args.subgrid:
        kwargs['write_grd']=True
        kwargs['grd_fn']=os.path.join(args.output.replace('.nc','_sub.grd'))
    if args.skip_nc:
        kwargs['write_nc']=False

    converter=DFlowToPTMHydro(args.mdu,args.output,**kwargs)

