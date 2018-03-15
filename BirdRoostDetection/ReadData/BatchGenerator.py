import os
import pandas
from BirdRoostDetection.ReadData import Labels
import numpy as np
from BirdRoostDetection import utils


class Batch_Generator():
    """This class organized the machine learning labels and creates ML batches.

    Class Variables:
        self.root_dir: The directory where the radar images are stored
        self.ml_sets: A dictionary containing a list of files that are part of
            the given ml set
        self.batch_size: the size of the minibatch learning batches
        self.label_dict: A dictionary of the labels, the key is the filename,
        and the value is a ML_Label object.
    """

    def __init__(self,
                 ml_label_csv,
                 ml_split_csv,
                 validate_k_index=3,
                 test_k_index=4,
                 default_batch_size=32,
                 root_dir=utils.RADAR_IMAGE_DIR,
                 high_memory_mode=False):
        self.label_dict = {}
        self.root_dir = root_dir
        self.no_roost_sets = {}
        self.roost_sets = {}
        self.no_roost_sets_V06 = {}
        self.roost_sets_V06 = {}
        self.__set_ml_sets(ml_split_csv,
                           validate_k_index,
                           test_k_index)

        ml_label_pd = pandas.read_csv(ml_label_csv)
        for index, row in ml_label_pd.iterrows():
            self.label_dict[row['AWS_file']] = Labels.ML_Label(row,
                                                               self.root_dir,
                                                               high_memory_mode)
        self.batch_size = default_batch_size

    def __set_ml_sets(self,
                      ml_split_csv,
                      validate_k_index,
                      test_k_index):
        """Create Train, test, and Validation set from k data folds.

        The k data folds are saved out to ml_split_csv. The fold at the given
        test and train indices as set to their corresponding set. The rest
        of the data is put into train. This method will initialize the following
        class variables: self.train, self.validation, and self.test. Each of
        these contains a list of filenames that correspond with the set.

        Args:
            ml_split_csv: A path to a csv file, where the csv has two columns,
            'AWS_file' and 'split_index'.
            validate_k_index: The index of the validation set.
            test_k_index: The index of the test set.
        """
        ml_split_pd = pandas.read_csv(ml_split_csv)
        # Remove files that weren't found
        all_files = utils.getListOfFilesInDirectory(
            self.root_dir + '/All_Color',
            '.png')
        all_files_dict = {}
        for i in range(len(all_files)):
            all_files_dict[
                os.path.basename(all_files[i]).replace('.png', '')] = True

        for index, row in ml_split_pd.iterrows():
            if all_files_dict.get(row['AWS_file']) is None:
                ml_split_pd.drop(index, inplace=True)

        # Sort into train, test, and validation sets

        self.__set_ml_sets_helper(self.no_roost_sets, self.no_roost_sets_V06,
                                  ml_split_pd[ml_split_pd.Roost != True],
                                  validate_k_index, test_k_index)
        self.__set_ml_sets_helper(self.roost_sets, self.roost_sets_V06,
                                  ml_split_pd[ml_split_pd.Roost],
                                  validate_k_index, test_k_index)

    def __set_ml_sets_helper(self, ml_sets, ml_sets_V06, ml_split_pd, val_k,
                             test_k):
        no_val_pd = ml_split_pd[ml_split_pd.split_index != val_k]
        ml_sets[utils.ML_Set.training] = list(
            no_val_pd[no_val_pd.split_index != test_k]['AWS_file'])
        ml_sets[utils.ML_Set.validation] = list(
            ml_split_pd[ml_split_pd.split_index == val_k]['AWS_file'])
        ml_sets[utils.ML_Set.testing] = list(
            ml_split_pd[ml_split_pd.split_index == test_k]['AWS_file'])

        for key in ml_sets.keys():
            ml_sets_V06[key] = []
            for item in ml_sets[key]:
                if int(item[-1]) >= 6:
                    ml_sets_V06[key].append(item)

            np.random.shuffle(ml_sets[key])
            np.random.shuffle(ml_sets_V06[key])

    def __get_batch_indices(self, ml_sets, ml_set):
        indices = np.random.randint(low=0,
                                    high=len(ml_sets[ml_set]),
                                    size=self.batch_size / 2)
        return indices

    def get_batch_all_radar_products(self, ml_set, dualPol):
        """Get a batch of data for machine learning. This batch contains data
        with four channels in it, one for each radar product. For dualPol data
        this will be four radar products, and for legacy data this will be two
        radar products.

        Args:
            ml_set: ML_Set enum value, train, test, or validation.
            dualPol: Boolean, true if the data is dual pol, false if the radar
            data is legacy.

        Returns:
            train_data, ground_truth, filenames:
                The ground truth is an array of batch size, where each item
                in the array contains a single ground truth label.
                The train_data is an array of images, corresponding to the
                ground truth values.
                filenames is an array of filenames, corresponding to the
                ground truth values.
        """
        ground_truths = []
        train_data = []
        filenames = []
        roost_sets = self.roost_sets
        no_roost_sets = self.no_roost_sets
        if dualPol:
            roost_sets = self.roost_sets_V06
            no_roost_sets = self.no_roost_sets_V06
        for ml_sets in [roost_sets, no_roost_sets]:
            indices = self.__get_batch_indices(ml_sets, ml_set)
            for index in indices:
                filename = ml_sets[ml_set][index]
                filenames.append(filename)
                is_roost = int(self.label_dict[filename].is_roost)
                images = []
                if dualPol:
                    radar_products = utils.Radar_Products
                else:
                    radar_products = utils.Legacy_radar_products
                for radar_product in radar_products:
                    image = self.label_dict[filename].get_image(radar_product)
                    images.append(image)
                ground_truths.append([is_roost, 1 - is_roost])
                train_data.append(images)
        # Update to channel last ordering
        train_data = np.rollaxis(np.array(train_data), 1, 4)
        return train_data, np.array(ground_truths), np.array(
            filenames)

    def get_batch_temporal(self):
        raise NotImplementedError

    def get_batch(self, ml_set, radar_product):
        """Get a batch of data for machine learning. As a default a batch
        contains data from for a single radar product.

        Args:
            ml_set: ML_Set enum value, train, test, or validation.
            radar_product: Radar_Product enum value, reflectivity, velocity,
                zdr, or rho_hv.

        Returns:
            train_data, ground_truth, filenames:
                The ground truth is an array of batch size, where each item
                in the array contains a single ground truth label.
                The train_data is an array of images, corresponding to the
                ground truth values.
                filenames is an array of filenames, corresponding to the
                ground truth values.
        """
        ground_truths = []
        train_data = []
        filenames = []
        roost_sets = self.roost_sets
        no_roost_sets = self.no_roost_sets
        if radar_product == utils.Radar_Products.cc or \
                        radar_product == utils.Radar_Products.diff_reflectivity:
            roost_sets = self.roost_sets_V06
            no_roost_sets = self.no_roost_sets_V06
        for ml_sets in [roost_sets, no_roost_sets]:
            indices = self.__get_batch_indices(ml_sets, ml_set)
            for index in indices:
                filename = ml_sets[ml_set][index]
                filenames.append(filename)
                is_roost = int(self.label_dict[filename].is_roost)
                image = self.label_dict[filename].get_image(radar_product)
                ground_truths.append([is_roost, 1 - is_roost])
                train_data.append(image)
        train_data_np = np.array(train_data)
        shape = train_data_np.shape
        train_data_np = train_data_np.reshape(shape[0], shape[1], shape[2], 1)
        return train_data_np, np.array(ground_truths), np.array(filenames)