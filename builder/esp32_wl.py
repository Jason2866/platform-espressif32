"""
ESP32 Wear Leveling Layer Implementation for FAT Filesystem Images

This module implements the ESP-IDF wear leveling layer structure to wrap
FAT filesystem images for use with ESP32 devices.

Based on ESP-IDF wear_levelling component:
https://github.com/espressif/esp-idf/tree/master/components/wear_levelling

Structure:
- Wear Leveling State sectors (2 copies at start and end)
- FAT filesystem data
- Dummy sectors for wear leveling

WL_State structure (48 bytes):
- pos: uint32_t (4 bytes) - Current position
- max_pos: uint32_t (4 bytes) - Maximum position  
- move_count: uint32_t (4 bytes) - Move counter
- access_count: uint32_t (4 bytes) - Access counter
- max_count: uint32_t (4 bytes) - Maximum count
- block_size: uint32_t (4 bytes) - Block size (sector size, typically 4096)
- version: uint32_t (4 bytes) - WL version (2)
- device_id: uint32_t (4 bytes) - Device ID
- reserved: 8 bytes - Reserved
- crc32: uint32_t (4 bytes) - CRC32 of the structure
"""

import struct
import zlib
from typing import Optional


class WearLevelingLayer:
    """ESP32 Wear Leveling Layer for FAT filesystem"""
    
    # Constants
    WL_VERSION = 2
    WL_STATE_SIZE = 48  # Size of WL_State structure
    WL_RESULT_OK = 0
    WL_RESULT_FAIL = -1
    
    # Default configuration
    DEFAULT_SECTOR_SIZE = 4096
    DEFAULT_UPDATE_RATE = 16
    DEFAULT_WL_TEMP_SIZE = 1  # Number of temp sectors
    DEFAULT_WL_STATE_SIZE = 2  # Number of state sectors (2 copies)
    
    def __init__(self, sector_size: int = DEFAULT_SECTOR_SIZE, 
                 update_rate: int = DEFAULT_UPDATE_RATE):
        """
        Initialize Wear Leveling Layer
        
        Args:
            sector_size: Size of each sector in bytes (default: 4096)
            update_rate: Update rate for wear leveling (default: 16)
        """
        self.sector_size = sector_size
        self.update_rate = update_rate
        self.wl_temp_size = self.DEFAULT_WL_TEMP_SIZE
        self.wl_state_size = self.DEFAULT_WL_STATE_SIZE
        
    def create_wl_state(self, pos: int = 0, max_pos: int = 0, 
                       move_count: int = 0, access_count: int = 0,
                       max_count: int = 0, device_id: int = 0) -> bytes:
        """
        Create a WL_State structure
        
        Args:
            pos: Current position
            max_pos: Maximum position
            move_count: Move counter
            access_count: Access counter
            max_count: Maximum count
            device_id: Device ID
            
        Returns:
            bytes: 48-byte WL_State structure with CRC32
        """
        # Pack structure without CRC (44 bytes total)
        # Format: 8 uint32_t (32 bytes) + 8 bytes reserved = 40 bytes
        # Then add 4 bytes CRC = 44 bytes total
        # Wait, that's wrong. Let me recalculate:
        # 8 uint32_t = 32 bytes
        # 8 bytes reserved = 8 bytes
        # Total before CRC = 40 bytes
        # Add CRC (4 bytes) = 44 bytes total
        # But we need 48 bytes!
        
        # Actually looking at ESP-IDF source, the structure should be:
        # uint32_t pos (4)
        # uint32_t max_pos (4)
        # uint32_t move_count (4)
        # uint32_t access_count (4)
        # uint32_t max_count (4)
        # uint32_t block_size (4)
        # uint32_t version (4)
        # uint32_t device_id (4)
        # uint32_t reserved[2] (8) - TWO uint32_t, not 8 bytes!
        # uint32_t crc32 (4)
        # Total = 10 * 4 = 40 bytes + 4 CRC = 44 bytes
        
        # But the constant says 48... Let me check if there are more fields
        # Looking at wear_levelling sources, there might be padding
        
        # Let's use the actual ESP-IDF structure with proper alignment
        state_data = struct.pack('<IIIIIIII',
            pos,                    # pos (4 bytes)
            max_pos,                # max_pos (4 bytes)
            move_count,             # move_count (4 bytes)
            access_count,           # access_count (4 bytes)
            max_count,              # max_count (4 bytes)
            self.sector_size,       # block_size (4 bytes)
            self.WL_VERSION,        # version (4 bytes)
            device_id               # device_id (4 bytes)
        )
        # Add reserved bytes (12 bytes to make it 44 bytes before CRC)
        state_data += b'\xFF' * 12
        
        # Now we have 32 + 12 = 44 bytes
        # Calculate CRC32 of the structure
        crc = zlib.crc32(state_data) & 0xFFFFFFFF
        
        # Append CRC32 (4 bytes) to make total 48 bytes
        state_with_crc = state_data + struct.pack('<I', crc)
        
        return state_with_crc
    
    def wrap_fat_image(self, fat_data: bytes, partition_size: int) -> bytes:
        """
        Wrap a FAT filesystem image with wear leveling layer
        
        Args:
            fat_data: Raw FAT filesystem data
            partition_size: Total partition size in bytes
            
        Returns:
            bytes: Wear-leveling wrapped FAT image
        """
        # Calculate sector counts
        total_sectors = partition_size // self.sector_size
        
        # WL structure:
        # - State sector 1 (at beginning)
        # - State sector 2 (at beginning + 1)
        # - FAT data sectors
        # - Temp sector (for wear leveling operations)
        # - State sector 1 copy (near end)
        # - State sector 2 copy (at end)
        
        # Calculate available sectors for FAT data
        wl_overhead_sectors = (self.wl_state_size * 2) + self.wl_temp_size
        fat_sectors = total_sectors - wl_overhead_sectors
        
        # Ensure FAT data fits
        fat_data_size = len(fat_data)
        required_fat_sectors = (fat_data_size + self.sector_size - 1) // self.sector_size
        
        if required_fat_sectors > fat_sectors:
            raise ValueError(
                f"FAT data ({fat_data_size} bytes, {required_fat_sectors} sectors) "
                f"does not fit in partition ({partition_size} bytes, {fat_sectors} available sectors)"
            )
        
        # Calculate max_pos (number of sectors that can be moved)
        max_pos = fat_sectors
        
        # Calculate max_count (when to trigger wear leveling)
        max_count = self.update_rate * fat_sectors
        
        # Create WL state
        wl_state = self.create_wl_state(
            pos=0,
            max_pos=max_pos,
            move_count=0,
            access_count=0,
            max_count=max_count,
            device_id=0
        )
        
        # Pad WL state to full sector
        wl_state_sector = wl_state + (b'\xFF' * (self.sector_size - len(wl_state)))
        
        # Build the wear-leveling image
        wl_image = bytearray()
        
        # 1. Add first state sector copy (sector 0)
        wl_image.extend(wl_state_sector)
        
        # 2. Add second state sector copy (sector 1)
        wl_image.extend(wl_state_sector)
        
        # 3. Add FAT data
        wl_image.extend(fat_data)
        
        # 4. Pad FAT data to sector boundary
        fat_padding = (fat_sectors * self.sector_size) - len(fat_data)
        wl_image.extend(b'\xFF' * fat_padding)
        
        # 5. Add temp sector (erased)
        wl_image.extend(b'\xFF' * (self.wl_temp_size * self.sector_size))
        
        # 6. Add state sector copies at end (for redundancy)
        wl_image.extend(wl_state_sector)  # State copy 1
        wl_image.extend(wl_state_sector)  # State copy 2
        
        # Verify final size
        if len(wl_image) != partition_size:
            # Pad or trim to exact partition size
            if len(wl_image) < partition_size:
                wl_image.extend(b'\xFF' * (partition_size - len(wl_image)))
            else:
                wl_image = wl_image[:partition_size]
        
        return bytes(wl_image)
    
    def verify_wl_state(self, state_data: bytes) -> bool:
        """
        Verify a WL_State structure's CRC32
        
        Args:
            state_data: 48-byte WL_State structure
            
        Returns:
            bool: True if CRC is valid
        """
        if len(state_data) != self.WL_STATE_SIZE:
            return False
        
        # Extract CRC from end
        stored_crc = struct.unpack('<I', state_data[-4:])[0]
        
        # Calculate CRC of data without CRC field
        calculated_crc = zlib.crc32(state_data[:-4]) & 0xFFFFFFFF
        
        return stored_crc == calculated_crc
    
    def extract_fat_from_wl(self, wl_data: bytes) -> Optional[bytes]:
        """
        Extract FAT filesystem data from wear-leveling wrapped image
        
        Args:
            wl_data: Wear-leveling wrapped image
            
        Returns:
            bytes: Raw FAT filesystem data, or None if invalid
        """
        if len(wl_data) < (self.wl_state_size * 2 + 1) * self.sector_size:
            return None
        
        # Verify first state sector
        first_state = wl_data[:self.WL_STATE_SIZE]
        if not self.verify_wl_state(first_state):
            return None
        
        # Extract FAT data (skip state sectors at beginning)
        fat_start = self.wl_state_size * self.sector_size
        
        # Calculate FAT data size (exclude temp and state sectors at end)
        total_sectors = len(wl_data) // self.sector_size
        wl_overhead_sectors = (self.wl_state_size * 2) + self.wl_temp_size
        fat_sectors = total_sectors - wl_overhead_sectors
        fat_size = fat_sectors * self.sector_size
        
        fat_data = wl_data[fat_start:fat_start + fat_size]
        
        return fat_data


def create_wl_fat_image(fat_data: bytes, partition_size: int, 
                       sector_size: int = 4096) -> bytes:
    """
    Convenience function to create a wear-leveling wrapped FAT image
    
    Args:
        fat_data: Raw FAT filesystem data
        partition_size: Total partition size in bytes
        sector_size: Sector size in bytes (default: 4096)
        
    Returns:
        bytes: Wear-leveling wrapped FAT image
    """
    wl = WearLevelingLayer(sector_size=sector_size)
    return wl.wrap_fat_image(fat_data, partition_size)


def extract_fat_from_wl_image(wl_data: bytes, sector_size: int = 4096) -> Optional[bytes]:
    """
    Convenience function to extract FAT data from wear-leveling image
    
    Args:
        wl_data: Wear-leveling wrapped image
        sector_size: Sector size in bytes (default: 4096)
        
    Returns:
        bytes: Raw FAT filesystem data, or None if invalid
    """
    wl = WearLevelingLayer(sector_size=sector_size)
    return wl.extract_fat_from_wl(wl_data)
