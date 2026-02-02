"""Advanced sybil attack detector using graph analysis and machine learning."""

from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import hashlib
import uuid
import numpy as np
import networkx as nx
from sklearn.metrics.pairwise import cosine_similarity
from networkx.algorithms import community


class SybilDetector:
    """Detects sybil attacks using multi-method graph analysis and ML."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the sybil detector.

        Args:
            config: Configuration for sybil detection
        """
        self.config = config or {
            'similarity_threshold': 0.95,  # High threshold for behavioral similarity
            'min_cluster_size': 3,
            'funding_threshold': 3,  # Min wallets from same source
            'temporal_window_seconds': 3600,  # 1 hour window
            'pattern_match_threshold': 3,
            'graph_density_threshold': 0.7,
            'pagerank_threshold': 0.05,
            'funding_pattern_weight': 0.3,
            'timing_pattern_weight': 0.25,
            'behavior_pattern_weight': 0.25,
            'network_pattern_weight': 0.2
        }

        # Graph structures
        self.funding_graph = nx.DiGraph()  # source -> destination
        self.interaction_graph = nx.Graph()  # wallet <-> wallet interactions
        self.similarity_graph = nx.Graph()  # weighted by behavioral similarity

        # Storage
        self.known_clusters = {}
        self.wallet_features = {}  # Cached feature vectors
        self.wallet_signatures = {}  # Transaction pattern signatures
        self.wallet_creation_times = {}

        # Metrics
        self.stats = {
            'clusters_detected': 0,
            'total_wallets_analyzed': 0,
            'graph_nodes': 0,
            'graph_edges': 0,
            'analysis_cycles': 0
        }

    def analyze_wallets(self, wallet_data: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run comprehensive sybil detection on wallet dataset.

        Args:
            wallet_data: Dict mapping wallet addresses to their data

        Returns:
            List of detected sybil clusters with confidence scores
        """
        self.stats['analysis_cycles'] += 1
        self.stats['total_wallets_analyzed'] = len(wallet_data)

        all_clusters = []

        # Build graphs from wallet data
        self._build_graphs(wallet_data)

        # Method 1: Funding source detection
        funding_clusters = self._detect_common_funding_sources()
        all_clusters.extend(funding_clusters)

        # Method 2: Behavioral similarity
        similarity_clusters = self._detect_behavioral_similarity(wallet_data)
        all_clusters.extend(similarity_clusters)

        # Method 3: Temporal correlation
        temporal_clusters = self._detect_temporal_correlation()
        all_clusters.extend(temporal_clusters)

        # Method 4: Transaction pattern fingerprinting
        pattern_clusters = self._detect_pattern_matches(wallet_data)
        all_clusters.extend(pattern_clusters)

        # Method 5: Community detection (Louvain)
        community_clusters = self._detect_communities()
        all_clusters.extend(community_clusters)

        # Method 6: PageRank coordinator identification
        coordinator_info = self._identify_coordinators()

        # Merge overlapping clusters and add coordinator info
        merged_clusters = self._merge_clusters(all_clusters, coordinator_info)

        self.stats['clusters_detected'] = len(merged_clusters)
        self.known_clusters.update({c['cluster_id']: c for c in merged_clusters})

        return merged_clusters

    def _build_graphs(self, wallet_data: Dict[str, Dict[str, Any]]):
        """Build graph structures from wallet data."""
        for wallet_addr, data in wallet_data.items():
            # Add to interaction graph
            if wallet_addr not in self.interaction_graph:
                self.interaction_graph.add_node(wallet_addr)

            # Build funding graph
            if 'funding_source' in data and data['funding_source']:
                source = data['funding_source']
                self.funding_graph.add_edge(source, wallet_addr)

            # Store creation time
            if 'creation_time' in data:
                self.wallet_creation_times[wallet_addr] = data['creation_time']

            # Build interaction edges from transactions
            if 'transactions' in data:
                for tx in data['transactions']:
                    if tx.get('type') == 'transfer' and 'to' in tx:
                        target = tx['to']
                        if target in wallet_data:  # Only internal network
                            weight = tx.get('amount_sol', 0)
                            if self.interaction_graph.has_edge(wallet_addr, target):
                                self.interaction_graph[wallet_addr][target]['weight'] += weight
                            else:
                                self.interaction_graph.add_edge(wallet_addr, target, weight=weight)

        self.stats['graph_nodes'] = self.interaction_graph.number_of_nodes()
        self.stats['graph_edges'] = self.interaction_graph.number_of_edges()

    def _detect_common_funding_sources(self) -> List[Dict[str, Any]]:
        """Detect wallets funded from same source (Method 1)."""
        clusters = []
        funding_threshold = self.config['funding_threshold']

        # Find funding sources with multiple destinations
        for source in self.funding_graph.nodes():
            funded_wallets = list(self.funding_graph.successors(source))

            if len(funded_wallets) >= funding_threshold:
                cluster = {
                    'cluster_id': str(uuid.uuid4()),
                    'detection_method': 'funding_source',
                    'sybil_confidence': 0.85,
                    'wallets': funded_wallets,
                    'cluster_size': len(funded_wallets),
                    'evidence': {
                        'common_funding_source': source,
                        'funding_count': len(funded_wallets)
                    },
                    'first_detected': datetime.utcnow().isoformat(),
                    'risk_level': self._calculate_risk_level(0.85)
                }
                clusters.append(cluster)

        return clusters

    def _detect_behavioral_similarity(self, wallet_data: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect wallets with similar behavior using cosine similarity (Method 2)."""
        clusters = []

        # Extract feature vectors
        wallet_addresses = []
        feature_vectors = []

        for wallet_addr, data in wallet_data.items():
            features = self._extract_behavioral_features(data)
            if features is not None:
                wallet_addresses.append(wallet_addr)
                feature_vectors.append(features)
                self.wallet_features[wallet_addr] = features

        if len(feature_vectors) < 2:
            return clusters

        # Calculate similarity matrix
        feature_matrix = np.array(feature_vectors)
        similarity_matrix = cosine_similarity(feature_matrix)

        # Find highly similar pairs
        threshold = self.config['similarity_threshold']
        similar_groups = defaultdict(set)

        for i in range(len(wallet_addresses)):
            for j in range(i + 1, len(wallet_addresses)):
                if similarity_matrix[i][j] >= threshold:
                    wallet_i = wallet_addresses[i]
                    wallet_j = wallet_addresses[j]
                    similar_groups[wallet_i].add(wallet_j)
                    similar_groups[wallet_j].add(wallet_i)

                    # Add to similarity graph
                    self.similarity_graph.add_edge(
                        wallet_i, wallet_j, 
                        weight=float(similarity_matrix[i][j])
                    )

        # Form clusters from connected components
        if similar_groups:
            # Build temporary graph
            temp_graph = nx.Graph()
            for wallet, similar_wallets in similar_groups.items():
                for similar in similar_wallets:
                    temp_graph.add_edge(wallet, similar)

            # Find connected components
            for component in nx.connected_components(temp_graph):
                if len(component) >= self.config['min_cluster_size']:
                    wallets_list = list(component)
                    avg_similarity = self._calculate_avg_similarity(wallets_list, similarity_matrix, wallet_addresses)

                    cluster = {
                        'cluster_id': str(uuid.uuid4()),
                        'detection_method': 'behavioral_similarity',
                        'sybil_confidence': min(0.90, avg_similarity),
                        'wallets': wallets_list,
                        'cluster_size': len(wallets_list),
                        'evidence': {
                            'behavioral_similarity_score': float(avg_similarity),
                            'feature_correlation': 'high'
                        },
                        'first_detected': datetime.utcnow().isoformat(),
                        'risk_level': self._calculate_risk_level(avg_similarity)
                    }
                    clusters.append(cluster)

        return clusters

    def _extract_behavioral_features(self, wallet_data: Dict[str, Any]) -> Optional[np.ndarray]:
        """Extract 6-dimensional behavioral feature vector."""
        try:
            features = [
                wallet_data.get('early_buy_rate', 0.0),
                wallet_data.get('avg_transaction_time', 0.0) / 3600.0,  # Normalize to hours
                wallet_data.get('avg_hold_time', 0.0) / 86400.0,  # Normalize to days
                wallet_data.get('avg_transaction_size', 0.0) / 10.0,  # Normalize SOL
                wallet_data.get('trade_frequency', 0.0),
                wallet_data.get('win_rate', 0.0)
            ]
            return np.array(features, dtype=np.float32)
        except Exception:
            return None

    def _calculate_avg_similarity(self, wallets: List[str], similarity_matrix: np.ndarray, 
                                 wallet_addresses: List[str]) -> float:
        """Calculate average similarity within a cluster."""
        indices = [wallet_addresses.index(w) for w in wallets if w in wallet_addresses]
        if len(indices) < 2:
            return 0.0

        similarities = []
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                similarities.append(similarity_matrix[indices[i]][indices[j]])

        return float(np.mean(similarities)) if similarities else 0.0

    def _detect_temporal_correlation(self) -> List[Dict[str, Any]]:
        """Detect wallets created in same time window (Method 3)."""
        clusters = []
        temporal_window = self.config['temporal_window_seconds']

        # Group by time buckets
        time_buckets = defaultdict(list)
        for wallet, creation_time in self.wallet_creation_times.items():
            if isinstance(creation_time, str):
                creation_time = datetime.fromisoformat(creation_time.replace('Z', '+00:00'))

            # Round to hour bucket
            bucket = creation_time.replace(minute=0, second=0, microsecond=0)
            time_buckets[bucket].append(wallet)

        # Find clusters
        min_size = max(self.config['min_cluster_size'], 5)  # At least 5 for temporal
        for bucket_time, wallets in time_buckets.items():
            if len(wallets) >= min_size:
                cluster = {
                    'cluster_id': str(uuid.uuid4()),
                    'detection_method': 'temporal_correlation',
                    'sybil_confidence': 0.75,
                    'wallets': wallets,
                    'cluster_size': len(wallets),
                    'evidence': {
                        'creation_time_window': temporal_window,
                        'bucket_timestamp': bucket_time.isoformat()
                    },
                    'first_detected': datetime.utcnow().isoformat(),
                    'risk_level': self._calculate_risk_level(0.75)
                }
                clusters.append(cluster)

        return clusters

    def _detect_pattern_matches(self, wallet_data: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect wallets with identical transaction patterns (Method 4)."""
        clusters = []

        # Create signatures
        for wallet_addr, data in wallet_data.items():
            if 'transactions' in data:
                signature = self._create_transaction_signature(data['transactions'])
                self.wallet_signatures[wallet_addr] = signature

        # Group by signature
        signature_groups = defaultdict(list)
        for wallet, signature in self.wallet_signatures.items():
            signature_groups[signature].append(wallet)

        # Find matching patterns
        threshold = self.config['pattern_match_threshold']
        for signature, wallets in signature_groups.items():
            if len(wallets) >= threshold:
                cluster = {
                    'cluster_id': str(uuid.uuid4()),
                    'detection_method': 'pattern_fingerprint',
                    'sybil_confidence': 0.90,
                    'wallets': wallets,
                    'cluster_size': len(wallets),
                    'evidence': {
                        'transaction_pattern_match': signature[:16],  # First 16 chars
                        'pattern_uniqueness': 'identical'
                    },
                    'first_detected': datetime.utcnow().isoformat(),
                    'risk_level': self._calculate_risk_level(0.90)
                }
                clusters.append(cluster)

        return clusters

    def _create_transaction_signature(self, transactions: List[Dict[str, Any]]) -> str:
        """Create unique signature from transaction pattern."""
        pattern = []
        for tx in sorted(transactions, key=lambda x: x.get('timestamp', 0)):
            tx_type = tx.get('type', 'unknown')
            amount = tx.get('amount_sol', 0.0)
            token = tx.get('token', 'unknown')[:8]  # First 8 chars
            pattern.append(f"{tx_type}:{amount:.2f}:{token}")

        pattern_str = '|'.join(pattern[:20])  # First 20 transactions
        return hashlib.sha256(pattern_str.encode()).hexdigest()

    def _detect_communities(self) -> List[Dict[str, Any]]:
        """Detect dense communities using Louvain algorithm (Method 5)."""
        clusters = []

        if self.interaction_graph.number_of_nodes() < 3:
            return clusters

        try:
            # Detect communities
            communities_found = community.louvain_communities(self.interaction_graph, seed=42)

            # Analyze each community
            for comm in communities_found:
                if len(comm) >= self.config['min_cluster_size']:
                    subgraph = self.interaction_graph.subgraph(comm)
                    density = nx.density(subgraph)

                    if density >= self.config['graph_density_threshold']:
                        cluster = {
                            'cluster_id': str(uuid.uuid4()),
                            'detection_method': 'community_detection',
                            'sybil_confidence': 0.80,
                            'wallets': list(comm),
                            'cluster_size': len(comm),
                            'evidence': {
                                'graph_density': float(density),
                                'community_algorithm': 'louvain'
                            },
                            'first_detected': datetime.utcnow().isoformat(),
                            'risk_level': self._calculate_risk_level(0.80)
                        }
                        clusters.append(cluster)
        except Exception as e:
            # Community detection can fail on certain graph structures
            pass

        return clusters

    def _identify_coordinators(self) -> Dict[str, Dict[str, float]]:
        """Identify coordinator wallets using PageRank (Method 6)."""
        coordinator_info = {}

        if self.interaction_graph.number_of_nodes() == 0:
            return coordinator_info

        try:
            # Calculate PageRank
            pagerank_scores = nx.pagerank(self.interaction_graph, alpha=0.85)

            # Calculate centrality metrics
            degree_centrality = nx.degree_centrality(self.interaction_graph)

            # Identify high-PageRank nodes
            threshold = self.config['pagerank_threshold']
            for wallet, score in pagerank_scores.items():
                if score >= threshold:
                    coordinator_info[wallet] = {
                        'pagerank': float(score),
                        'degree_centrality': float(degree_centrality.get(wallet, 0.0)),
                        'is_coordinator': True,
                        'coordinator_confidence': 0.90
                    }
        except Exception:
            pass

        return coordinator_info

    def _merge_clusters(self, clusters: List[Dict[str, Any]], 
                       coordinator_info: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
        """Merge overlapping clusters and add coordinator information."""
        if not clusters:
            return []

        # Build wallet -> clusters mapping
        wallet_to_clusters = defaultdict(list)
        for i, cluster in enumerate(clusters):
            for wallet in cluster['wallets']:
                wallet_to_clusters[wallet].append(i)

        # Merge clusters with significant overlap (>50% shared wallets)
        merged = []
        used_indices = set()

        for i, cluster in enumerate(clusters):
            if i in used_indices:
                continue

            # Find overlapping clusters
            overlapping = set([i])
            for wallet in cluster['wallets']:
                for other_idx in wallet_to_clusters[wallet]:
                    if other_idx != i and other_idx not in used_indices:
                        overlap_size = len(set(cluster['wallets']) & set(clusters[other_idx]['wallets']))
                        if overlap_size >= len(cluster['wallets']) * 0.5:
                            overlapping.add(other_idx)

            # Merge
            all_wallets = set()
            methods = set()
            confidences = []
            evidence_combined = {}

            for idx in overlapping:
                all_wallets.update(clusters[idx]['wallets'])
                methods.add(clusters[idx]['detection_method'])
                confidences.append(clusters[idx]['sybil_confidence'])
                evidence_combined.update(clusters[idx]['evidence'])
                used_indices.add(idx)

            # Calculate aggregated confidence
            avg_confidence = np.mean(confidences)
            multi_method_bonus = len(methods) * 0.02  # 2% per method
            final_confidence = min(0.99, avg_confidence + multi_method_bonus)

            # Find coordinator
            coordinator_wallet = None
            coordinator_score = 0.0
            for wallet in all_wallets:
                if wallet in coordinator_info:
                    if coordinator_info[wallet]['pagerank'] > coordinator_score:
                        coordinator_wallet = wallet
                        coordinator_score = coordinator_info[wallet]['pagerank']

            merged_cluster = {
                'cluster_id': str(uuid.uuid4()),
                'detection_method': '+'.join(sorted(methods)),
                'sybil_confidence': float(final_confidence),
                'wallets': list(all_wallets),
                'cluster_size': len(all_wallets),
                'evidence': evidence_combined,
                'coordinator_wallet': coordinator_wallet,
                'coordinator_pagerank': float(coordinator_score) if coordinator_wallet else 0.0,
                'first_detected': datetime.utcnow().isoformat(),
                'last_updated': datetime.utcnow().isoformat(),
                'risk_level': self._calculate_risk_level(final_confidence),
                'detection_method_count': len(methods)
            }

            merged.append(merged_cluster)

        return merged

    def _calculate_risk_level(self, confidence: float) -> str:
        """Calculate risk level from confidence score."""
        if confidence >= 0.85:
            return 'critical'
        elif confidence >= 0.75:
            return 'high'
        elif confidence >= 0.60:
            return 'medium'
        else:
            return 'low'

    def get_wallet_sybil_score(self, wallet_address: str) -> float:
        """Get sybil probability score for individual wallet.

        Returns:
            Float between 0.0 and 1.0 indicating sybil probability
        """
        max_score = 0.0

        for cluster in self.known_clusters.values():
            if wallet_address in cluster['wallets']:
                max_score = max(max_score, cluster['sybil_confidence'])

        return max_score

    def get_stats(self) -> Dict[str, Any]:
        """Get detector statistics."""
        avg_cluster_size = 0.0
        highest_score = 0.0

        if self.known_clusters:
            avg_cluster_size = np.mean([c['cluster_size'] for c in self.known_clusters.values()])
            highest_score = max([c['sybil_confidence'] for c in self.known_clusters.values()])

        return {
            'clusters_detected': self.stats['clusters_detected'],
            'total_wallets_analyzed': self.stats['total_wallets_analyzed'],
            'graph_nodes': self.stats['graph_nodes'],
            'graph_edges': self.stats['graph_edges'],
            'avg_cluster_size': float(avg_cluster_size),
            'highest_sybil_score': float(highest_score),
            'analysis_cycles': self.stats['analysis_cycles']
        }
