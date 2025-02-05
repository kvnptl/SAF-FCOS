from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import json
import os
import sys

import numpy as np
from numpy import asarray
from nuscenes.nuscenes import NuScenes
from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser(description='Convert dataset')
    parser.add_argument('--dataset', help="convert dataset to coco-style", default='nuscenes', type=str)
    parser.add_argument('--datadir', help="data dir for annotations to be converted",
                        default='/home/citybuster/Data/nuScenes', type=str)
    parser.add_argument('--outdir', help="output dir for json files",
                        default='/home/citybuster/Data/nuScenes/v1.0-trainval', type=str)

    return parser.parse_args()


def xyxy_to_xywh(xyxy_box):
    xmin, ymin, xmax, ymax = xyxy_box
    TO_REMOVE = 1
    xywh_box = (xmin, ymin, xmax - xmin + TO_REMOVE, ymax - ymin + TO_REMOVE)
    return xywh_box


def xyxy_to_polygn(xyxy_box):
    xmin, ymin, xmax, ymax = xyxy_box
    xywh_box = [[xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax]]
    return xywh_box


def calculate_mean_std_of_img(img):
    img = asarray(img)
    # convert from integers to floats
    img = img.astype('float64')
    means = img.mean(axis=(0, 1), dtype='float64')
    stds = img.std(axis=(0, 1), dtype='float64')
    return means, stds


def extract(data_dir, out_dir):
    """merge detection results and convert results to COCO"""

    # Load mini dataset, and dataset, the mini dataset is used as test and valid dataset
    nusc_mini = NuScenes(version='v1.0-mini', dataroot=data_dir, verbose=True)
    nusc = NuScenes(version='v1.0-trainval', dataroot=data_dir, verbose=True)
    sample_files_mini = [s['filename'] for s in nusc_mini.sample_data if (s['channel'] == 'CAM_FRONT') and
                         s['is_key_frame']]
    sample_files = [s['filename'] for s in nusc.sample_data if (s['channel'] == 'CAM_FRONT') and
                    s['is_key_frame']]
    sample_files_mini = set(sample_files_mini)
    sample_files = set(sample_files)

    # Filter dataset items, ensure the mini dataset and dataset are not cross
    tmp_sample_files = []
    for item in sample_files:
        if item not in sample_files_mini:
            tmp_sample_files.append(item)
        else:
            continue

    train_sample_files = tmp_sample_files
    tv_sample_files = sample_files_mini

    with open(os.path.join(data_dir, 'v1.0-trainval', 'image_pc_annotations.json'), 'r') as f:
        sample_labels = json.load(f)

    train_annos = list()
    tv_annos = list()

    for i, annos in tqdm(enumerate(sample_labels)):
        if len(annos) > 0:
            sample_data_token = annos[0]['sample_data_token']
            sample_data = nusc.get('sample_data', sample_data_token)
            im_file_name = sample_data['filename']
            if im_file_name in train_sample_files:
                train_annos.append(annos)
            elif im_file_name in tv_sample_files:
                tv_annos.append(annos)
            else:
                sys.exit("Something wrong with the generate json labels, Please check your code carefully.")

    sets = ['train', ]
    all_annos = [train_annos, ]
    json_name = 'gt_fcos_coco_%s_%02d.json'
    radius_list = [7]
    for radius in radius_list:
        for data_set, set_annos in zip(sets, all_annos):
            print('Starting %s, Radius %02d' % (data_set, radius))
            num_item = 0
            norm_param = {}
            pc_im_means = None
            pc_im_stds = None
            for annos in tqdm(set_annos):
                if len(annos) > 0:
                    num_item += 1
                    image = dict()

                    image['width'] = 1600
                    image['height'] = 900

                    sample_data_token = annos[0]['sample_data_token']
                    sample_data = nusc.get('sample_data', sample_data_token)
                    sample = nusc.get('sample', sample_data['sample_token'])
                    pointsensor_token = sample['data']['RADAR_FRONT']
                    pc_rec = nusc.get('sample_data', pointsensor_token)

                    image['file_name'] = sample_data['filename']
                    image['pc_file_name'] = pc_rec['filename'].replace('samples', 'imagepc_%02d' % radius).replace(
                        'pcd', 'json')
                    # check if the image file exists
                    if not os.path.isfile(os.path.join(data_dir, image['pc_file_name'])):
                        print('File not exist: %s' % image['pc_file_name'])
                        continue
                    with open(os.path.join(data_dir, image['pc_file_name']), 'r') as f:
                        image_info = json.load(f)

                    if num_item == 1:
                        pc_im_means, pc_im_stds = np.asarray(image_info['mean']), np.asarray(image_info['std'])
                    else:
                        tmp_pc_im_means, tmp_pc_im_stds = np.asarray(image_info['mean']), np.asarray(image_info['std'])

                        pc_im_means = (num_item - 1) / num_item * pc_im_means + tmp_pc_im_means / num_item
                        pc_im_stds = (num_item - 1) / num_item * pc_im_stds + tmp_pc_im_stds / num_item

            norm_param['pc_im_means'] = [item for item in pc_im_means]
            norm_param['pc_im_stds'] = [item for item in pc_im_stds]
            with open(os.path.join(out_dir, 'norm_info', 'norm_param_' + json_name % (data_set, radius)),
                      'w') as outfile:
                outfile.write(json.dumps(norm_param))


if __name__ == '__main__':
    args = parse_args()
    if args.dataset == "nuscenes":
        extract(args.datadir, args.outdir)
    else:
        print("Dataset not supported: %s" % args.dataset)
