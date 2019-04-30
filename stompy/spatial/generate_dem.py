"""
Command line interface to generating a DEM from a collections of
source data described in a shapefile.
"""
from stompy.spatial import field
import os, glob
import numpy as np
import logging
import subprocess
log=logging.getLogger("generate_dem")

# global variable holding the composite field
dataset=None

def create_dataset(args):
    """
    Parse the shapefile and source definitions, but do not render
    any of the DEM.
    """
    paths=args.path

    # field.CompositeField has a generic interface for sources, via
    # a 'factory' method.
    def factory(attrs):
        geo_bounds=attrs['geom'].bounds

        if attrs['src_name'].startswith('py:'):
            expr=attrs['src_name'][3:]
            # something like 'ConstantField(-1.0)'
            # a little sneaky... make it look like it's running
            # after a "from stompy.spatial.field import *"
            # and also it gets fields of the shapefile
            field_hash=dict(field.__dict__)
            # convert the attrs into a dict suitable for passing to eval
            attrs_dict={}
            for name in attrs.dtype.names:
                attrs_dict[name]=attrs[name]
            return eval(expr,field_hash,attrs_dict)
        
        # Otherwise assume src_name is a file name or file pattern.
        for p in paths:
            full_path=os.path.join(p,attrs['src_name'])
            files=glob.glob(full_path)
            if len(files)>1:
                mrf=field.MultiRasterField(files)
                return mrf
            elif len(files)==1:
                gg=field.GdalGrid(files[0],geo_bounds=geo_bounds)
                gg.default_interpolation='linear'
                return gg
        
        log.warning("Source %s was not found -- ignoring"%attrs['src_name'])
        return None
    
    comp_field=field.CompositeField(shp_fn=args.shapefile,
                                    factory=factory,
                                    priority_field='priority',
                                    data_mode='data_mode',
                                    alpha_mode='alpha_mode')
    return comp_field


def process_tile(args,overwrite=False):
    fn,xxyy,res = args

    bleed=150 # pad out the tile by this much to avoid edge effects

    if overwrite or (not os.path.exists(fn)):
        #try:
        xxyy_pad=[ xxyy[0]-bleed,
                   xxyy[1]+bleed,
                   xxyy[2]-bleed,
                   xxyy[3]+bleed ]
        dem=dataset.to_grid(dx=res,dy=res,bounds=xxyy_pad)

        if bleed!=0:
            dem=dem.crop(xxyy)
        if overwrite and os.path.exists(fn):
            os.unlink(fn)
        dem._projection=dataset.projection
        dem.write_gdal(fn)
    else:
        log.info("File exists")

def config_logging(args):
    levels=[logging.ERROR,logging.WARNING,logging.INFO,logging.DEBUG]
    if args.verbose>=len(levels): level=levels[-1]
    else: level=levels[args.verbose]
    log.setLevel(level)
    handler=logging.StreamHandler()
    log.addHandler(handler)
    bf = logging.Formatter('[{asctime} {name} {levelname:8s}] {message}',
                           style='{')
    handler.setFormatter(bf)
    for handler in log.handlers:
        handler.setLevel(level)

##

    
if __name__=='__main__':
    import argparse

    parser=argparse.ArgumentParser(description='Generate DEM from multiple sources.')

    parser.add_argument("-s", "--shapefile", help="Shapefile defining sources")
    parser.add_argument("-o", "--output", help="Directory for writing output", default="output")
    parser.add_argument("-p", "--path", help="Add to search path for source datasets",
                        action='append',default=["."])
    parser.add_argument("-m", "--merge", help="Merge the tiles once all have been rendered",action='store_true')
    parser.add_argument("-r", "--resolution", help="Output resolution", default=10.0,type=float)
    parser.add_argument("-b", "--bounds",help="Bounds for output xmin xmax ymin ymax",nargs=4,type=float)
    parser.add_argument("-t", "--tilesize",help="Make tiles NxN",default=1000,type=int)
    parser.add_argument("-v", "--verbose",help="Increase verbosity",default=1,action='count')
    parser.add_argument("-f", "--force",help="Overwrite existing tiles",action='store_true')

    args=parser.parse_args()

    config_logging(args)
    
    dataset=create_dataset(args)

    dem_dir=args.output
    if not os.path.exists(dem_dir):
        log.info("Creating output directory %s"%dem_dir)
        os.makedirs(dem_dir)

    res=args.resolution
    tile_x=tile_y=res*args.tilesize

    total_bounds=args.bounds
    # round out to tiles
    total_tile_bounds= [np.floor(total_bounds[0]/tile_x) * tile_x,
                        np.ceil(total_bounds[1]/tile_x) * tile_x,
                        np.floor(total_bounds[2]/tile_y) * tile_y,
                        np.ceil(total_bounds[3]/tile_y) * tile_y ]

    calls=[]
    for x0 in np.arange(total_tile_bounds[0],total_tile_bounds[1],tile_x):
        for y0 in np.arange(total_tile_bounds[2],total_tile_bounds[3],tile_y):
            xxyy=(x0,x0+tile_x,y0,y0+tile_y)
            fn=os.path.join(dem_dir,"tile_res%g_%.0f_%.0f.tif"%(res,x0,y0))
            calls.append( [fn,xxyy,res] )

    log.info("%d tiles"%len(calls))
    
    if 0:
        # this won't work for now, as dataset is created in the __main__ stanza
        p = Pool(4)
        p.map(f, calls )
    else:
        for i,call in enumerate(calls):
            log.info("Call %d/%d %s"%(i,len(calls),call[0]))
            process_tile(call,overwrite=args.force)

    if args.merge:
        # and then merge them with something like:
        # if the file exists, its extents will not be updated.
        output_fn=os.path.join(dem_dir,'merged.tif')
        os.path.exists(output_fn) and os.unlink(output_fn)
        log.info("Merging using gdal_merge.py")
        
        # Try importing gdal_merge directly, which will more reliably
        # find the right library since if we got this far, python already
        # found gdal okay.  Unfortunately it's not super straightforward
        # to get the right way of importing this, since it's intended as
        # a script and not a module.
        try:
            from Scripts import gdal_merge
        except ImportError:
            log.warning("Failed to import gdal_merge, will try subprocess",exc_info=True)
            gdal_merge=None

        tiles=glob.glob("%s/tile*.tif"%dem_dir)
        cmd=["python","gdal_merge.py","-init","nan","-a_nodata","nan",
             "-o",output_fn]+tiles
        
        log.info(" ".join(cmd))
                
        if gdal_merge:
            gdal_merge.main(argv=cmd[1:])
        else:
            subprocess.call(" ".join(cmd),shell=True)


