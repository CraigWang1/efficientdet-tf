"""
Utils module to work with VOC2007 dataset

Download the dataset from here: 
    http://host.robots.ox.ac.uk/pascal/VOC/voc2007/index.html
"""

from pathlib import Path
from functools import partial
from typing import Tuple, Sequence, Union

import tensorflow as tf

import xml.etree.ElementTree as ET

import efficientdet.utils.io as io_utils
import efficientdet.utils.bndbox as bb_utils
from .preprocess import normalize_image

### I CHANGED THIS FOR THE BIN DATASET
IDX_2_LABEL = [
    'bin'
]
# IDX_2_LABEL = [
#     'person',
#     # Animals
#     'dog',
#     'bird',
#     'cat',
#     'cow',
#     'horse',
#     'sheep',
#     # Vehicle
#     'aeroplane',
#     'bicycle',
#     'boat',
#     'bus',
#     'car',
#     'motorbike',
#     'train',
#     # Indoor
#     'bottle',
#     'chair',
#     'diningtable',
#     'pottedplant',
#     'sofa',
#     'tvmonitor',
# ]

LABEL_2_IDX = {l: i for i, l in enumerate(IDX_2_LABEL)}


def _read_voc_annot(annot_path: str) -> Tuple[Sequence[int], 
                                              Sequence[tf.Tensor]]:
    # Reads a voc annotation and returns
    # a list of tuples containing the ground 
    # truth boxes and its respective label
    root = ET.parse(annot_path).getroot()
    image_size = (int(root.findtext('size/height')), 
                  int(root.findtext('size/width')))

    boxes = root.findall('object')
    bbs = []
    labels = []

    for b in boxes:
        bb = b.find('bndbox')
        bb = (int(bb.findtext('xmin')), 
              int(bb.findtext('ymin')), 
              int(bb.findtext('xmax')), 
              int(bb.findtext('ymax')))
        bbs.append(bb)
        labels.append(LABEL_2_IDX[b.findtext('name')])

    bbs = tf.stack(bbs)
    bbs = bb_utils.normalize_bndboxes(bbs, image_size)

    return labels, bbs


def _annot_gen(annot_file: Sequence[Path]):
    for f in annot_file:
        yield _read_voc_annot(str(f))


def _scale_boxes(labels: tf.Tensor, boxes: tf.Tensor, 
                 to_size: Tuple[int, int]):
    h, w = to_size

    x1, y1, x2, y2 = tf.split(boxes, 4, axis=1)
    x1 *= w
    x2 *= w
    y1 *= h
    y2 *= h
    
    return labels, tf.concat([x1, y1, x2, y2], axis=1)


def build_dataset(dataset_path: Union[str, Path],
                  im_input_size: Tuple[int, int],
                  shuffle: bool = True,
                  batch_size: int = 2) -> tf.data.Dataset:
    """
    Create model input pipeline using tensorflow datasets

    Parameters
    ----------
    dataset_path: Union[Path, str]
        Path to the voc2007 dataset. The dataset path should contain
        two subdirectories, one called images and another one called 
        annots
    im_input_size: Tuple[int, int]
        Model input size. Images will automatically be resized to this
        shape
    batch_size: int, default 2
        Training model batch size
    
    Examples
    --------
    
    >>> ds = build_dataset('data/VOC2007', im_input_size=(128, 128))

    >>> for images, (labels, bbs) in ds.take(1):
    ...   print(images.shape)
    ...   print(labels, bbs.shape)
    ...
    (2, 128, 128)
    ([[1, 0]
      [13, -1]], (2, 2, 4))

    Returns
    -------
    tf.data.Dataset

    """
    dataset_path = Path(dataset_path)
    im_path = dataset_path / 'JPEGImages'
    annot_path = dataset_path / 'Annotations'

    # List sorted annotation files
    annot_files = sorted(annot_path.glob('*.xml'))
    
    # Partially evaluate image loader to resize images
    # always with the same shape
    load_im = partial(io_utils.load_image, im_size=im_input_size)
    scale_boxes = partial(_scale_boxes, to_size=im_input_size)

    # We assume that tf datasets list files sorted when shuffle=False
    im_ds = (tf.data.Dataset.list_files(str(im_path / '*.png'),           #######I CHANGED TO PNG 
                                        shuffle=False)
             .map(load_im).map(normalize_image))
    annot_ds = (tf.data.Dataset
                .from_generator(generator=lambda: _annot_gen(annot_files), 
                                output_types=(tf.int32, tf.float32))
                .map(scale_boxes))

    # Join both datasets
    ds = (tf.data.Dataset.zip((im_ds, annot_ds))
          .padded_batch(batch_size=batch_size,
                        padded_shapes=((*im_input_size, 3), 
                                       ((None,), (None, 4))),
                        padding_values=(0., (-1, 0.))))
    
    if shuffle:
        ds = ds.shuffle(128)
    
    return ds
