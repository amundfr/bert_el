from typing import List, Tuple, Iterable
from random import sample
from os.path import isdir, isfile, join

from torch.utils.data import TensorDataset, Subset, \
        DataLoader, RandomSampler, SequentialSampler
from torch import Tensor, load, save, cat


class DatasetGenerator:
    def __init__(self,
                 input_ids: Tensor = Tensor(),
                 attention_mask: Tensor = Tensor(),
                 token_type_ids: Tensor = Tensor(),
                 labels: Tensor = Tensor()):
        # The data tensors
        self.input_ids = input_ids
        self.attention_mask = attention_mask
        self.token_type_ids = token_type_ids
        self.labels = labels
        # Place holders for TensorDataset objects
        self.dataset = None
        self.balanced_dataset = None
        # Lists saying which document index a data point
        # in the respective datasets come from
        self.dataset_to_doc = []
        self.balanced_dataset_to_doc = []
        # Subsets of a dataset defined in split_dataset
        self.train_dataset = None
        self.val_dataset = None
        self.test_dataset = None
        # Default directory and files to save and load tensors
        self.file_dir = 'data/vectors'
        self.file_names = ['data_vectors_input_ids.pt',
                           'data_vectors_attention_mask.pt',
                           'data_vectors_token_type_ids.pt',
                           'data_vectors_labels.pt']

    def read_from_directory(self, dir: str = 'data/vectors'):
        if not isdir(dir):
            print(f"Could not find directory at {dir}.")
            return

        if not all([isfile(join(dir, f)) for f in self.file_names]):
            print(f"Could not find all files in directory at {dir}."
                  " Try function read_vectors_from_file.")
            return

        self.file_dir = dir
        self.input_ids = load(join(dir, self.file_names[0]))
        self.attention_mask = load(join(dir, self.file_names[1]))
        self.token_type_ids = load(join(dir, self.file_names[2]))
        self.labels = load(join(dir, self.file_names[3]))

    def read_from_files(self,
                        f_input_ids: str = 'data_vectors_input_ids.pt',
                        f_attention_mask: str = 'data_vectors_attention_mask.pt',
                        f_token_type_ids: str = 'data_vectors_token_type_ids.pt',
                        f_labels: str = 'data_vectors_labels.pt',
                        directory: str = 'data/vectors'
                        ):
        self.file_names = [f_input_ids, f_attention_mask,
                           f_token_type_ids, f_labels]
        self.file_dir = directory
        self.read_from_directory(self.file_dir)

    def write_to_files(self, dir: str = 'data/vectors'):
        print(f"Writing vectors to directory {dir}...")
        save(self.input_ids, self.file_names[0])
        save(self.attention_mask, self.file_names[1])
        save(self.token_type_ids, self.file_names[2])
        save(self.labels, self.file_names[3])

    def get_tensor_dataset(self):
        if not self.dataset:
            self.dataset = TensorDataset(self.input_ids, self.attention_mask,
                                self.token_type_ids, self.labels)
        return self.dataset

    def get_balanced_dataset(self, docs_entities: List, n_neg: int = 1)\
            -> TensorDataset:
        """
        Create a smaller, balanced dataset with up to n_neg negative
        sample for each entity.

        :param docs_entities: the docs_entities property from ConllToCandidates
        :param n_neg: the number of negative samples to include for each entity.
            Set to 1 for a more or less balanced dataset
        :returns: A TensorDataset with all positive labels and up to n_neg
            negative labels for each entity
        """
        if self.balanced_dataset:
            return self.balanced_dataset

        full_dataset = self.get_tensor_dataset()

        balanced_tensors = [Tensor().to(dtype=full_dataset[0][0].dtype),
                            Tensor().to(dtype=full_dataset[0][1].dtype),
                            Tensor().to(dtype=full_dataset[0][2].dtype),
                            Tensor().to(dtype=full_dataset[0][3].dtype)]

        # List of which doc each data sample comes from. Same length as the respective datasets
        # For the full dataset
        self.dataset_to_doc = []
        # For the balanced_dataset
        self.balanced_dataset_to_doc = []

        # Points at indices in the full dataset
        full_dataset_idx = 0
        for i, doc_entities in enumerate(docs_entities):
            # Iterate Named Entities in current doc
            for entity_info in doc_entities:
                # Skip 'B'-entities (entities not in KB)
                if entity_info['GroundTruth'] != 'B' and entity_info['Candidates']:

                    # All these candidates belong to current doc
                    self.dataset_to_doc.append([i] * len(entity_info['Candidates']))

                    # Add any positive datapoint (i.e. where candidate is ground truth)
                    if entity_info['GroundTruth'] in entity_info['Candidates']:
                        gt_idx = full_dataset_idx + entity_info['Candidates'].index(entity_info['GroundTruth'])

                        # Keep track of which document this comes from
                        self.balanced_dataset_to_doc.append(i)

                        # Append to all four input vectors
                        for j in range(len(balanced_tensors)):
                            balanced_tensors[j] = cat([
                                balanced_tensors[j],
                                full_dataset[gt_idx][j].view(1, -1)
                            ], dim=0)

                    # Candidates that are not the ground truth
                    neg_cands = [c for c in entity_info['Candidates'] if c != entity_info['GroundTruth']]
                    # Sample all or up to n_neg candidates
                    n_sample = min(n_neg, len(neg_cands))
                    # Sample candidates
                    random_cands = sample(neg_cands, n_sample)

                    for random_cand in random_cands:
                        # Index of the tensors corresponding to this candidate
                        cand_idx = full_dataset_idx + entity_info['Candidates'].index(random_cand)

                        # Keep track of which document this comes from
                        self.balanced_dataset_to_doc.append(i)

                        # Append to all four input vectors
                        for j in range(len(balanced_tensors)):
                            balanced_tensors[j] = cat([
                                    balanced_tensors[j],
                                    full_dataset[cand_idx][j].view(1, -1)
                                    ], dim=0
                                )

                    # Move index pointer to the next entity's data points
                    full_dataset_idx += len(entity_info['Candidates'])

        self.balanced_dataset = TensorDataset(balanced_tensors[0],
                                              balanced_tensors[1],
                                              balanced_tensors[2],
                                              balanced_tensors[3])
        return self.balanced_dataset


    def get_split_dataset(self, split_ratios: Iterable, dataset: str = 'balanced')\
            -> Tuple[Subset, Subset, Subset]:
        """
        Splits the dataset in given ratios to train, validation and test subsets
        Splits on the documents that the data is from, rather than the datapoints,
        so the exact ratio of the subsets may not be as expected.
        This requires that the functions to initialize the datasets have already been run

        :param split_ratios: the ratios of the train, validation, and split respectively
            as an iterable of three ratio values
        :param dataset: 'full' or 'balanced' respectively for the full or the balanced dataset
        :returns: three torch Subset with training, validation and test data
        """
        if dataset == 'balanced':
            dataset_to_doc = self.balanced_dataset_to_doc
            dataset = self.balanced_dataset
        else:
            dataset_to_doc = self.dataset_to_doc
            dataset = self.dataset

        # Number of different docs
        n_docs = len(set(dataset_to_doc))

        # ratio of training data, base 1
        train_ratio = split_ratios[0] / sum(split_ratios)
        n_train = int(train_ratio * n_docs)
        # ratio of validation data, base 1
        val_ratio = split_ratios[1] / sum(split_ratios)
        n_val = int(val_ratio * n_docs)
        # the rest is test data
        n_test = n_docs - n_train - n_val

        # Keeping track of the indices in the dataset
        # These are used to define the final Subset
        train_indices = []
        val_indices = []
        test_indices = []

        for i, doc_idx in enumerate(dataset_to_doc):
            if doc_idx < n_train:
                train_indices.append(i)
            elif doc_idx < (n_train + n_val):
                val_indices.append(i)
            else:
                test_indices.append(i)

        print(f"({train_indices[0]: >6}, {train_indices[-1]: >6})   training set slice, "
              f"{(train_indices[-1] - train_indices[0]) / n_train: >6.1f} candidates on average per document")
        print(f"({val_indices[0]: >6}, {val_indices[-1]: >6}) validation set slice, "
              f"{(val_indices[-1] - val_indices[0]) / n_val: >6.1f} candidates on average per document")
        print(f"({test_indices[0]: >6}, {test_indices[-1]: >6})       test set slice, "
              f"{(test_indices[-1] - test_indices[0]) / n_test: >6.1f} candidates on average per document")

        self.train_dataset = Subset(dataset, train_indices)
        self.val_dataset = Subset(dataset, val_indices)
        self.test_dataset = Subset(dataset, test_indices)
        return self.train_dataset, self.val_dataset, self.test_dataset

    def get_data_loaders(self, batch_size: int = 32):
        """
        Using the subsets from get_split_dataset, this makes a DataLoader for each subset

        :param batch_size: batch size for all data loaders
        :returns: a Tuple of three DataLoader
        """
        if not (self.train_dataset and self.val_dataset and self.test_dataset):
            print("The split datasets have not been initialized."
                  "Please try the function get_split_dataset first.")
            return

        # Random sampling of training data
        train_dataloader = DataLoader(
                self.train_dataset,  # The training samples.
                sampler=RandomSampler(self.train_dataset),  # Select batches randomly
                batch_size=batch_size  # Trains with this batch size.
            )

        # Sequential sampling of validation data
        validation_dataloader = DataLoader(
                self.val_dataset,
                sampler=SequentialSampler(self.val_dataset),
                batch_size=batch_size
            )

        # Sequential sampling of test data
        test_dataloader = DataLoader(
                self.test_dataset,
                sampler=SequentialSampler(self.test_dataset),
                batch_size=batch_size
            )

        return train_dataloader, validation_dataloader, test_dataloader

    def print_size_of_vectors(self):
        size = sum(self.input_ids.element_size() * self.input_ids.nelement())
        size = sum(self.attention_mask.element_size() * self.attention_mask.nelement())
        size = sum(self.token_type_ids.element_size() * self.token_type_ids.nelement())
        size = sum(self.labels.element_size() * self.labels.nelement())

        print(f"Training data size (minimized): {size / 2 ** 20: .2f} MB")

    def print_token_sequence_stats(self):
        # Average length of the left and right sequences
        n_tots = []
        n_left_tokens = []
        n_right_tokens = []
        for att, tt, label in zip(self.attention_mask, self.token_type_ids, self.labels):
            n_tot = len(att[att])
            n_r = len(tt[tt])
            n_l = n_tot - n_r
            n_tots.append(n_tot)
            n_left_tokens.append(n_l)
            n_right_tokens.append(n_r)

        print(f"{sum(n_tots) / len(n_tots) :.1f} average number of tokens")
        print(f"{sum(n_left_tokens) / len(n_left_tokens) :.1f} average tokens in entity sequence.")
        print(f"Min: {min(n_left_tokens)}, max: {max(n_left_tokens)}")
        print(f"{sum(n_right_tokens) / len(n_right_tokens) :.1f} average tokens in candidate sequence.")
        print(f"Min: {min(n_right_tokens)}, max: {max(n_right_tokens)}")

    def get_dataset_balance_info(self):
        if not self.train_dataset:
            print("The split datasets have not been initialized."
                  "Please try the function get_split_dataset first.")
            return 0, 0
        # Statistics of the training set
        pos = 0
        neg = 0
        for d in self.train_dataset:
            pos += int(d[3])
            neg += int(not d[3])

        print(f"Negative labels: {neg:,}, positive: {pos:,}, negative/positive: {neg / pos:.3f}")
        return neg, pos