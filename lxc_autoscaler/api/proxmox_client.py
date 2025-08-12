"""Async Proxmox VE API client wrapper."""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

import aiohttp
from proxmoxer import ProxmoxAPI

from ..config.models import ProxmoxConfig
from .exceptions import (
    ProxmoxAPIError,
    ProxmoxAuthenticationError,
    ProxmoxConnectionError,
    ProxmoxOperationError,
    ProxmoxResourceNotFoundError,
    ProxmoxTimeoutError,
)


logger = logging.getLogger(__name__)


class ProxmoxClient:
    """Async wrapper for Proxmox VE API operations."""
    
    def __init__(self, config: ProxmoxConfig) -> None:
        """Initialize Proxmox client.
        
        Args:
            config: Proxmox connection configuration.
        """
        self.config = config
        self._api: Optional[ProxmoxAPI] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
        
    async def __aenter__(self) -> 'ProxmoxClient':
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
    
    async def connect(self) -> None:
        """Establish connection to Proxmox API."""
        try:
            logger.info(f"Connecting to Proxmox at {self.config.host}:{self.config.port}")
            
            # Create HTTP session
            connector = aiohttp.TCPConnector(
                verify_ssl=self.config.verify_ssl,
                limit=20,
                limit_per_host=10,
            )
            
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )
            
            # Initialize Proxmox API
            auth_kwargs = {
                'host': self.config.host,
                'port': self.config.port,
                'verify_ssl': self.config.verify_ssl,
                'timeout': self.config.timeout,
            }
            
            if self.config.token_name and self.config.token_value:
                # Token-based authentication
                auth_kwargs.update({
                    'user': self.config.user,
                    'token_name': self.config.token_name,
                    'token_value': self.config.token_value,
                })
            elif self.config.password:
                # Password-based authentication
                auth_kwargs.update({
                    'user': self.config.user,
                    'password': self.config.password,
                })
            else:
                raise ProxmoxAuthenticationError("No authentication method configured")
            
            self._api = ProxmoxAPI(**auth_kwargs)
            
            # Test connection
            await self._test_connection()
            
            logger.info("Successfully connected to Proxmox API")
            
        except Exception as e:
            logger.error(f"Failed to connect to Proxmox: {e}")
            await self.close()
            if isinstance(e, ProxmoxAPIError):
                raise
            raise ProxmoxConnectionError(f"Connection failed: {e}")
    
    async def close(self) -> None:
        """Close connection to Proxmox API."""
        if self._session:
            await self._session.close()
            self._session = None
        self._api = None
        logger.debug("Proxmox API connection closed")
    
    async def _test_connection(self) -> None:
        """Test API connection by retrieving version."""
        try:
            await self._make_request(self._api.version.get)
        except Exception as e:
            raise ProxmoxConnectionError(f"Connection test failed: {e}")
    
    async def _make_request(self, request_func, *args, **kwargs) -> Any:
        """Make async API request with error handling and rate limiting.
        
        Args:
            request_func: Proxmox API function to call.
            *args: Positional arguments for the request.
            **kwargs: Keyword arguments for the request.
            
        Returns:
            API response data.
            
        Raises:
            ProxmoxAPIError: If request fails.
        """
        if not self._api:
            raise ProxmoxConnectionError("Not connected to Proxmox API")
        
        async with self._semaphore:
            try:
                # Execute request in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None, 
                    lambda: request_func(*args, **kwargs)
                )
                return response
                
            except Exception as e:
                error_msg = str(e).lower()
                
                if "authentication" in error_msg or "unauthorized" in error_msg:
                    raise ProxmoxAuthenticationError(f"Authentication failed: {e}")
                elif "not found" in error_msg or "does not exist" in error_msg:
                    raise ProxmoxResourceNotFoundError(f"Resource not found: {e}")
                elif "timeout" in error_msg:
                    raise ProxmoxTimeoutError(f"Request timeout: {e}")
                elif "rate limit" in error_msg:
                    # Implement exponential backoff
                    await asyncio.sleep(1)
                    raise ProxmoxAPIError(f"Rate limit exceeded: {e}")
                else:
                    raise ProxmoxOperationError(f"API request failed: {e}")
    
    async def get_container_status(self, node: str, vmid: int) -> Dict[str, Any]:
        """Get LXC container status.
        
        Args:
            node: Proxmox node name.
            vmid: Container VMID.
            
        Returns:
            Container status information.
        """
        logger.debug(f"Getting status for container {vmid} on node {node}")
        return await self._make_request(
            self._api.nodes(node).lxc(vmid).status.current.get
        )
    
    async def get_container_config(self, node: str, vmid: int) -> Dict[str, Any]:
        """Get LXC container configuration.
        
        Args:
            node: Proxmox node name.
            vmid: Container VMID.
            
        Returns:
            Container configuration.
        """
        logger.debug(f"Getting config for container {vmid} on node {node}")
        return await self._make_request(
            self._api.nodes(node).lxc(vmid).config.get
        )
    
    async def get_container_rrd_data(
        self, 
        node: str, 
        vmid: int, 
        timeframe: str = "hour",
        cf: str = "AVERAGE"
    ) -> List[Dict[str, Any]]:
        """Get container RRD performance data.
        
        Args:
            node: Proxmox node name.
            vmid: Container VMID.
            timeframe: Time frame (hour, day, week, month, year).
            cf: Consolidation function (AVERAGE, MAX).
            
        Returns:
            RRD data points.
        """
        logger.debug(f"Getting RRD data for container {vmid} on node {node}")
        return await self._make_request(
            self._api.nodes(node).lxc(vmid).rrddata.get,
            timeframe=timeframe,
            cf=cf
        )
    
    async def update_container_config(
        self, 
        node: str, 
        vmid: int, 
        **config_params
    ) -> Dict[str, Any]:
        """Update LXC container configuration.
        
        Args:
            node: Proxmox node name.
            vmid: Container VMID.
            **config_params: Configuration parameters to update.
            
        Returns:
            Update operation result.
        """
        logger.info(f"Updating config for container {vmid} on node {node}: {config_params}")
        return await self._make_request(
            self._api.nodes(node).lxc(vmid).config.put,
            **config_params
        )
    
    async def resize_container(
        self, 
        node: str, 
        vmid: int, 
        cpu_cores: Optional[int] = None,
        memory_mb: Optional[int] = None
    ) -> Dict[str, Any]:
        """Resize container resources.
        
        Args:
            node: Proxmox node name.
            vmid: Container VMID.
            cpu_cores: New CPU core count.
            memory_mb: New memory size in MB.
            
        Returns:
            Resize operation result.
        """
        config_updates = {}
        
        if cpu_cores is not None:
            config_updates['cores'] = cpu_cores
        
        if memory_mb is not None:
            config_updates['memory'] = memory_mb
        
        if not config_updates:
            raise ValueError("At least one resource parameter must be specified")
        
        logger.info(f"Resizing container {vmid} on node {node}: {config_updates}")
        return await self.update_container_config(node, vmid, **config_updates)
    
    async def get_node_status(self, node: str) -> Dict[str, Any]:
        """Get Proxmox node status.
        
        Args:
            node: Node name.
            
        Returns:
            Node status information.
        """
        logger.debug(f"Getting status for node {node}")
        return await self._make_request(
            self._api.nodes(node).status.get
        )
    
    async def list_containers(self, node: str) -> List[Dict[str, Any]]:
        """List all LXC containers on a node.
        
        Args:
            node: Node name.
            
        Returns:
            List of containers.
        """
        logger.debug(f"Listing containers on node {node}")
        containers = await self._make_request(
            self._api.nodes(node).lxc.get
        )
        # Filter only LXC containers
        return [c for c in containers if c.get('type') == 'lxc']
    
    async def list_nodes(self) -> List[Dict[str, Any]]:
        """List all Proxmox nodes.
        
        Returns:
            List of nodes.
        """
        logger.debug("Listing Proxmox nodes")
        return await self._make_request(self._api.nodes.get)
    
    async def find_container_node(self, vmid: int) -> Optional[str]:
        """Find which node contains the specified container.
        
        Args:
            vmid: Container VMID.
            
        Returns:
            Node name if found, None otherwise.
        """
        nodes = await self.list_nodes()
        
        for node_info in nodes:
            node_name = node_info['node']
            try:
                containers = await self.list_containers(node_name)
                for container in containers:
                    if container.get('vmid') == vmid:
                        return node_name
            except ProxmoxResourceNotFoundError:
                continue
        
        return None
    
    async def get_cluster_resources(self) -> List[Dict[str, Any]]:
        """Get cluster resource usage information.
        
        Returns:
            Cluster resource data.
        """
        logger.debug("Getting cluster resources")
        return await self._make_request(self._api.cluster.resources.get)
    
    async def health_check(self) -> bool:
        """Perform health check on API connection.
        
        Returns:
            True if connection is healthy.
        """
        try:
            await self._make_request(self._api.version.get)
            return True
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False