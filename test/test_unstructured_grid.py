import numpy as np
import os
import nose
from nose.tools import assert_raise

from stompy.grid import unstructured_grid


def test_undo_00():
    ug=unstructured_grid.UnstructuredGrid()

    n1=ug.add_node(x=[0,0])
    n2=ug.add_node(x=[0,1])
    n3=ug.add_node(x=[0.67,0.5])

    e1=ug.add_edge(nodes=[n1,n2])
    e2=ug.add_edge(nodes=[n1,n3])
    cp=ug.checkpoint()
    e3=ug.add_edge(nodes=[n2,n3])
    c0=ug.add_cell(nodes=[n1,n2,n3])

    assert ug.Ncells()==1
    assert ug.Nedges()==3
    assert ug.Nnodes()==3
    
    ug.revert(cp)

    assert ug.Ncells()==0
    assert ug.Nedges()==2
    assert ug.Nnodes()==3

## 

sample_data=os.path.join(os.path.dirname(__file__),'data')

def test_toggle_toggle():
    ug=unstructured_grid.SuntansGrid(os.path.join(sample_data,'sfbay'))
    xy=(507872, 4159018)
    c=ug.select_cells_nearest(xy)
    nodes=ug.cell_to_nodes(c)
    chk=ug.checkpoint()
    ug.toggle_cell_at_point(xy)
    ug.revert(chk)
    ug.delete_node_cascade(nodes[0])

def test_delete_undelete():
    ug=unstructured_grid.SuntansGrid(os.path.join(sample_data,'sfbay'))
    xy=(507872, 4159018)
    c=ug.select_cells_nearest(xy)
    nodes=ug.cell_to_nodes(c)
    chk=ug.checkpoint()
    ug.delete_cell(c)
    ug.revert(chk)
    ug.delete_node_cascade(nodes[0])


## 

def test_triangle_from_scratch():
    ug=unstructured_grid.UnstructuredGrid(max_sides=4)

    n1=ug.add_node(x=[0,0])
    n2=ug.add_node(x=[1,0])
    n3=ug.add_node(x=[1,1])

    j1=ug.add_edge(nodes=[n1,n2])
    j2=ug.add_edge(nodes=[n2,n3])
    j3=ug.add_edge(nodes=[n3,n1])

    c1=ug.toggle_cell_at_point([0.2,0.2])

def test_quad_from_scratch():
    ug=unstructured_grid.UnstructuredGrid(max_sides=4)

    n1=ug.add_node(x=[0,0])
    n2=ug.add_node(x=[1,0])
    n3=ug.add_node(x=[1,1])
    n4=ug.add_node(x=[0,1])

    j1=ug.add_edge(nodes=[n1,n2])
    j2=ug.add_edge(nodes=[n2,n3])
    j3=ug.add_edge(nodes=[n3,n4])
    j4=ug.add_edge(nodes=[n4,n1])

    c1=ug.toggle_cell_at_point([0.2,0.2])
    # and remove it..
    ug.toggle_cell_at_point([0.2,0.2])


def test_duplicate_edge():
    ug=unstructured_grid.UnstructuredGrid(max_sides=4)

    n1=ug.add_node(x=[0,0])
    n2=ug.add_node(x=[1,0])

    j1=ug.add_edge(nodes=[n1,n2])

    with assert_raises(unstructured_grid.GridException) as cm:
        j2=ug.add_edge(nodes=[n2,n1])

## 

def test_merge_nodes():
    gt=unstructured_grid.UnstructuredGrid()

    gt.add_rectilinear([0,0],[2,2],3,3)

    c_dupe=3

    new_nodes=[ gt.add_node(x=gt.nodes['x'][n] + np.r_[0.1,0.1] )
                for n in gt.cells['nodes'][c_dupe] ]
    gt.modify_cell(c_dupe,nodes=new_nodes)
    gt.make_edges_from_cells()
    gt.delete_orphan_nodes() 
    gt.renumber_nodes()

    # at this point, need to merge three pairs of nodes:
    # 4 and 8 -- this is the central pair, of the tree.
    # 5 and 11
    # 7 and 9

    gt.merge_nodes(7,9)
    gt.merge_nodes(5,11)
    gt.merge_nodes(4,8)


##         
def test_pickle():
    ug=unstructured_grid.UnstructuredGrid(max_sides=4)
    def cb(*a,**k):
        pass
    ug.subscribe_after('add_node',cb)
    chk=ug.checkpoint()

    n1=ug.add_node(x=[0,0])
    n2=ug.add_node(x=[1,0])

    j1=ug.add_edge(nodes=[n1,n2])

    ug.write_pickle('blah.pkl')
    ug2=unstructured_grid.UnstructuredGrid.from_pickle('blah.pkl')


## 

def test_modify_max_sides():
    ug=unstructured_grid.SuntansGrid('/home/rusty/src/umbra/Umbra/sample_data/sfbay')

    ug.modify_max_sides(max_sides=6)
    
    n1=ug.add_node(x=[0,0])
    n2=ug.add_node(x=[1,0])
    n3=ug.add_node(x=[1,1])
    n4=ug.add_node(x=[0,1])

    ug.add_cell_and_edges(nodes=[n1,n2,n3,n4])

    ug.modify_max_sides(max_sides=4)

    with assert_raises(unstructured_grid.GridException) as cm:
        ug.modify_max_sides(max_sides=3)

## 
    
if __name__=='__main__':
    nose.main()
