from typing import Iterator, Optional


class ConllToken:
    def __init__(self,
                 text: str,
                 tag: str,
                 true_label: str,
                 predicted_label: Optional[str]):
        self.text = text
        self.tag = tag
        self.true_label = true_label
        self.predicted_label = predicted_label

    def get_truth(self) -> str:
        return "\\".join((self.text, self.tag, self.true_label))

    def set_predicted_label(self, label: str):
        self.predicted_label = label

    def get_predicted(self) -> str:
        return "\\".join((self.text, self.tag, self.predicted_label))


class ConllDocument:
    def __init__(self, raw: str):
        document_values = raw.split("\t")
        if len(document_values) == 2:
            id, ground_truth = document_values
            predictions = None
        elif len(document_values) == 3:
            id, ground_truth, predictions = document_values
        else:
            raise Exception("Unable to parse IOB document:\n%s" % raw)
        self.id = id
        raw_tokens = ground_truth.split()
        predicted_tokens_raw = predictions.split() if predictions is not None else None
        self.tokens = []
        for i in range(len(raw_tokens)):
            raw_token = raw_tokens[i]
            text, tag, label = raw_token.split("\\")
            if predicted_tokens_raw is None:
                predicted_label = None
            else:
                predicted_label = predicted_tokens_raw[i].split("\\")[-1]
            self.tokens.append(ConllToken(text, tag, label, predicted_label))

    def text(self):
        return ' '.join([token.text for token in self.tokens])

    def get_truth(self):
        return ' '.join([token.get_truth() for token in self.tokens])

    def get_predicted(self):
        return ' '.join([token.get_predicted() for token in self.tokens])


def conll_documents(f: str) -> Iterator[ConllDocument]:
    for line in open(f):
        document = ConllDocument(line[:-1])
        yield document
