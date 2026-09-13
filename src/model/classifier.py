"""
src/model/classifier.py

Intent Classifier model module using Word-level TF-IDF (1-2 n-grams) with Logistic Regression.
"""

import os, re, json, csv
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

class IntentClassifier:
    """Word-level TF-IDF (1-2 n-grams) + Logistic Regression Intent Classifier."""

    def __init__(self, c_val: float = 1.0, class_weight: str = 'balanced'):
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
        self.model = LogisticRegression(C=c_val, max_iter=1000, class_weight=class_weight, solver='lbfgs')
        self.is_trained = False
        self.classes_ = []

    def fit(self, texts: list, labels: list):
        if not texts or not labels:
            raise ValueError("Training texts and labels cannot be empty.")
        X = self.vectorizer.fit_transform(texts)
        self.model.fit(X, labels)
        self.classes_ = list(self.model.classes_)
        self.is_trained = True
        return self

    def predict(self, texts: list) -> list:
        if not self.is_trained:
            raise RuntimeError("Model must be trained before calling predict.")
        X = self.vectorizer.transform(texts)
        return list(self.model.predict(X))

    def predict_proba(self, texts: list) -> list:
        if not self.is_trained:
            raise RuntimeError("Model must be trained before calling predict_proba.")
        X = self.vectorizer.transform(texts)
        probs = self.model.predict_proba(X)
        results = []
        for prob_row in probs:
            max_p = max(prob_row)
            pred_idx = list(prob_row).index(max_p)
            pred_label = self.classes_[pred_idx]
            results.append((pred_label, float(max_p)))
        return results
