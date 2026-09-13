"""
reconstruct_conversations.py — Reusable conversation reconstruction module.

Transforms raw TWCS tweets into structured conversation-level records.

This module is designed to be imported by other scripts or used directly.
It does NOT modify the raw data.

Usage:
    from src.data.reconstruct_conversations import ConversationReconstructor
    
    reconstructor = ConversationReconstructor()
    reconstructor.build_index()  # reads full CSV, builds tweet graph
    conversations = reconstructor.get_brand_conversations("SpotifyCares")
"""

import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Optional

import pandas as pd

from src.data.data_utils import iter_chunks, CHUNK_SIZE


def parse_timestamp(ts_str: str) -> Optional[datetime]:
    """Parse Twitter-style timestamp: 'Tue Oct 31 22:10:47 +0000 2017'"""
    if pd.isna(ts_str) or not isinstance(ts_str, str) or not ts_str.strip():
        return None
    try:
        return datetime.strptime(ts_str.strip(), "%a %b %d %H:%M:%S %z %Y")
    except (ValueError, TypeError):
        return None


class ConversationReconstructor:
    """
    Builds an in-memory tweet graph from the TWCS CSV and reconstructs
    conversation threads.

    Conversation structure:
        - Each conversation has a root tweet (no in_response_to_tweet_id)
        - Children are linked via in_response_to_tweet_id → parent tweet_id
        - Threads are walked via BFS from the root
        - Messages are sorted chronologically within each thread
    """

    def __init__(self):
        self.tweets = {}                    # tweet_id → record dict
        self.children = defaultdict(list)   # parent_id → [child_ids]
        self.roots = set()                  # tweet_ids with no parent
        self._indexed = False

    def build_index(self, progress_interval: int = 500_000):
        """
        Read the full CSV in chunks and build the tweet graph.

        After calling this, self.tweets, self.children, and self.roots
        are populated.
        """
        print("Building tweet index from CSV...")
        t0 = time.time()
        row_count = 0

        for chunk in iter_chunks():
            for _, row in chunk.iterrows():
                tid = str(row["tweet_id"]).strip()

                parent_raw = row["in_response_to_tweet_id"]
                parent = None
                if pd.notna(parent_raw):
                    parent = str(parent_raw).strip()
                    # Handle float-like strings: '3.0' → '3'
                    if "." in parent:
                        try:
                            parent = str(int(float(parent)))
                        except (ValueError, OverflowError):
                            parent = None
                    if parent in ("nan", "", "None"):
                        parent = None

                record = {
                    "tweet_id": tid,
                    "author_id": (
                        str(row["author_id"]).strip()
                        if pd.notna(row["author_id"]) else ""
                    ),
                    "inbound": bool(row["inbound"]),
                    "created_at": (
                        str(row["created_at"]).strip()
                        if pd.notna(row["created_at"]) else ""
                    ),
                    "text": (
                        str(row["text"]).strip()
                        if pd.notna(row["text"]) else ""
                    ),
                    "in_response_to_tweet_id": parent,
                }

                self.tweets[tid] = record

                if parent:
                    self.children[parent].append(tid)
                else:
                    self.roots.add(tid)

                row_count += 1

            if row_count % progress_interval < CHUNK_SIZE:
                elapsed = time.time() - t0
                print(f"  ... indexed {row_count:,} tweets ({elapsed:.1f}s)")

        elapsed = time.time() - t0
        self._indexed = True
        print(f"  Index complete: {row_count:,} tweets, "
              f"{len(self.roots):,} roots ({elapsed:.1f}s)")

    def walk_thread(self, root_id: str) -> list[dict]:
        """
        BFS from root_id, collecting all connected tweets.
        Returns list of tweet dicts sorted by timestamp.
        """
        thread = []
        visited = set()
        queue = [root_id]

        while queue:
            tid = queue.pop(0)
            if tid in visited:
                continue
            visited.add(tid)

            if tid in self.tweets:
                thread.append(self.tweets[tid])

            for child_id in self.children.get(tid, []):
                if child_id not in visited:
                    queue.append(child_id)

        # Sort by parsed timestamp
        def sort_key(t):
            dt = parse_timestamp(t["created_at"])
            if dt is None:
                return datetime.min
            # Return naive datetime for consistent comparison
            return dt.replace(tzinfo=None)

        thread.sort(key=sort_key)
        return thread

    def build_conversation(self, thread: list[dict], conv_id: str) -> dict:
        """
        Build a structured conversation record from a list of tweet dicts.
        """
        customer_msgs = []
        brand_msgs = []
        brand_authors = set()
        customer_authors = set()

        for msg in thread:
            if msg["inbound"]:
                customer_msgs.append(msg)
                customer_authors.add(msg["author_id"])
            else:
                brand_msgs.append(msg)
                brand_authors.add(msg["author_id"])

        return {
            "conversation_id": conv_id,
            "message_count": len(thread),
            "customer_message_count": len(customer_msgs),
            "brand_message_count": len(brand_msgs),
            "has_customer_message": len(customer_msgs) > 0,
            "has_brand_response": len(brand_msgs) > 0,
            "brand_author_ids": sorted(brand_authors),
            "customer_author_ids": sorted(customer_authors),
            "start_time": thread[0]["created_at"] if thread else "",
            "end_time": thread[-1]["created_at"] if thread else "",
            "messages": thread,
        }

    def get_all_conversations(
        self,
        brand_filter: Optional[str] = None,
        min_messages: int = 1,
        require_both_sides: bool = False,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """
        Reconstruct all conversations, optionally filtered.

        Parameters
        ----------
        brand_filter : str, optional
            Only include conversations where this author_id appears
            as a brand (outbound) participant.
        min_messages : int
            Minimum number of messages in the thread.
        require_both_sides : bool
            If True, only include conversations with both customer
            and brand messages.
        limit : int, optional
            Maximum number of conversations to return.
        """
        if not self._indexed:
            raise RuntimeError("Call build_index() first.")

        conversations = []
        for root_id in self.roots:
            thread = self.walk_thread(root_id)

            if len(thread) < min_messages:
                continue

            conv_id = f"conv_{root_id}"
            conv = self.build_conversation(thread, conv_id)

            if brand_filter:
                if brand_filter not in conv["brand_author_ids"]:
                    continue

            if require_both_sides:
                if not (conv["has_customer_message"] and conv["has_brand_response"]):
                    continue

            conversations.append(conv)

            if limit and len(conversations) >= limit:
                break

        return conversations

    def get_brand_conversations(
        self,
        brand_id: str,
        min_messages: int = 2,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """
        Convenience: get conversations for a specific brand with at least
        2 messages and both customer + brand participation.
        """
        return self.get_all_conversations(
            brand_filter=brand_id,
            min_messages=min_messages,
            require_both_sides=True,
            limit=limit,
        )

    def get_brand_stats(self, brand_id: str, conversations: list[dict]) -> dict:
        """Compute summary statistics for a brand's conversations."""
        total = len(conversations)
        if total == 0:
            return {"total_conversations": 0}

        import statistics

        msg_counts = [c["message_count"] for c in conversations]
        cust_counts = [c["customer_message_count"] for c in conversations]
        brand_counts = [c["brand_message_count"] for c in conversations]

        multi_turn = sum(1 for c in conversations if c["message_count"] >= 3)

        return {
            "total_conversations": total,
            "multi_turn_3plus": multi_turn,
            "message_count_mean": round(statistics.mean(msg_counts), 2),
            "message_count_median": statistics.median(msg_counts),
            "message_count_max": max(msg_counts),
            "customer_msg_mean": round(statistics.mean(cust_counts), 2),
            "brand_msg_mean": round(statistics.mean(brand_counts), 2),
        }
