"""YAML structure walking and Renovate comment detection.

This module provides utilities for traversing YAML structures and extracting
Renovate-style version comments while preserving the original YAML structure.

Renovate comments are YAML comments that specify how to check for version updates:
    # renovate: datasource=docker depName=kindest/node
    # renovate: datasource=helm depName=traefik repositoryUrl=https://traefik.github.io/charts

The main function walk_yaml_for_renovate() recursively traverses both CommentedMap
(YAML dicts) and CommentedSeq (YAML lists) structures, extracting comments from
various positions:
- Before a key: applies to the next item
- After a key: applies to the current item
- On list items: applies to the item

Important: Uses ruamel.yaml's comment tracking via .ca attribute to preserve
comment positions. Tracks processed comments to avoid duplicates.

This is critical for loko's `config upgrade` command, which uses these comments
to know which components to check for version updates.
"""
from typing import Optional
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from .parsers import parse_renovate_comment


def walk_yaml_for_renovate(data, updates, path="", processed_comments=None):
    """
    Recursively walk YAML structure looking for renovate comments.
    Only processes each comment once and associates it with the correct value.
    """
    if processed_comments is None:
        processed_comments = set()

    if isinstance(data, CommentedMap):
        keys = list(data.keys())
        for i, key in enumerate(keys):
            value = data[key]
            current_path = f"{path}.{key}" if path else str(key)

            # Only check for renovate comments on scalar values (not nested structures)
            if not isinstance(value, (CommentedMap, CommentedSeq)):
                renovate_info = None

                # Check if the PREVIOUS key has a comment in position [2] (after that key)
                # That comment should apply to THIS (current) key
                if i > 0 and hasattr(data, 'ca') and data.ca.items:
                    prev_key = keys[i - 1]
                    prev_comment_token = data.ca.items.get(prev_key)
                    # Position [2] is "after" - contains comments after the previous key's value
                    if prev_comment_token and len(prev_comment_token) > 2 and prev_comment_token[2]:
                        comment_obj = prev_comment_token[2]
                        if comment_obj and hasattr(comment_obj, 'value'):
                            comment_text = comment_obj.value
                            comment_id = (id(data), prev_key, 'after_to', key)
                            if comment_id not in processed_comments:
                                parsed = parse_renovate_comment(comment_text)
                                if parsed:
                                    renovate_info = parsed
                                    processed_comments.add(comment_id)

                if renovate_info:
                    updates.append((current_path, key, renovate_info, value, data))

            # Recurse into nested structures
            if isinstance(value, (CommentedMap, CommentedSeq)):
                walk_yaml_for_renovate(value, updates, current_path, processed_comments)

    elif isinstance(data, CommentedSeq):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"

            # For list items that are dicts with single key-value (like "- traefik: 37.3.0")
            if isinstance(item, CommentedMap) and len(item) == 1:
                item_key = list(item.keys())[0]
                item_value = item[item_key]

                renovate_info = None

                # For the first item, check the sequence's comment
                if idx == 0 and hasattr(data, 'ca') and hasattr(data.ca, 'comment'):
                    if data.ca.comment and len(data.ca.comment) > 1 and data.ca.comment[1]:
                        comment_list = data.ca.comment[1]
                        for comment_obj in (comment_list if isinstance(comment_list, list) else [comment_list]):
                            if comment_obj and hasattr(comment_obj, 'value'):
                                comment_text = comment_obj.value
                                comment_id = (id(data), 'seq_comment', idx)
                                if comment_id not in processed_comments:
                                    parsed = parse_renovate_comment(comment_text)
                                    if parsed:
                                        renovate_info = parsed
                                        processed_comments.add(comment_id)
                                        break

                # For subsequent items, check the previous item's key comment (position [2])
                if not renovate_info and idx > 0:
                    prev_item = data[idx - 1]
                    if isinstance(prev_item, CommentedMap) and len(prev_item) == 1:
                        prev_key = list(prev_item.keys())[0]
                        if hasattr(prev_item, 'ca') and prev_item.ca.items:
                            comment_token = prev_item.ca.items.get(prev_key)
                            if comment_token and len(comment_token) > 2 and comment_token[2]:
                                comment_obj = comment_token[2]
                                if comment_obj and hasattr(comment_obj, 'value'):
                                    comment_text = comment_obj.value
                                    comment_id = (id(prev_item), prev_key, 'after')
                                    if comment_id not in processed_comments:
                                        parsed = parse_renovate_comment(comment_text)
                                        if parsed:
                                            renovate_info = parsed
                                            processed_comments.add(comment_id)

                if renovate_info:
                    updates.append((current_path, item_key, renovate_info, item_value, item))

            # Recurse into more complex nested structures
            elif isinstance(item, (CommentedMap, CommentedSeq)):
                walk_yaml_for_renovate(item, updates, current_path, processed_comments)
