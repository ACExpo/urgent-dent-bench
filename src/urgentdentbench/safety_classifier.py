"""Baseline second-stage safety classifier.

This module is deliberately simple. It should only be trained after expert labels
for model responses exist. It uses TF-IDF + logistic regression as a transparent
baseline against which embedding/transformer approaches can be compared.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

def make_baseline():
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1,2), min_df=2, max_features=30000)),
        ("clf", LogisticRegression(max_iter=3000, class_weight="balanced")),
    ])
