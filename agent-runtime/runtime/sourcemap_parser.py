"""Minimal source map parser - replaces broken sourcemap library.
Parses Vite's standard JSON source maps to resolve minified errors
back to original source files and line numbers."""

import json
import re

_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

def _vlq_decode(value):
    result = 0
    shift = 0
    for char in value:
        if char not in _B64:
            break
        integer = _B64.index(char)
        if integer & 32:
            integer = -(integer & 31)
        result |= (integer & 31) << shift
        shift += 5
        if not (integer & 32):
            break
    return result


def parse_source_map(map_json):
    """Parse a Vite source map JSON and return a lookup function.
    
    Returns: lookup(gen_line, gen_col) -> (source_file, source_line) or None
    """
    if isinstance(map_json, str):
        map_json = json.loads(map_json)
    
    sources = map_json.get("sources", [])
    mappings = map_json.get("mappings", "")
    
    if not mappings or not sources:
        return None
    
    # Parse VLQ mappings into a lookup table
    # Key: (generated_line, generated_col) -> (source_idx, source_line, source_col)
    lookup_table = {}
    
    gen_line = 1
    prev_source_idx = 0
    prev_source_line = 0
    prev_source_col = 0
    prev_gen_col = 0
    
    for line_str in mappings.split(";"):
        if not line_str.strip():
            gen_line += 1
            prev_gen_col = 0
            continue
        
        segments = line_str.split(",")
        for segment in segments:
            if not segment:
                continue
            
            values = []
            for char in segment:
                if char in _B64:
                    values.append(_vlq_decode(char))
                # Move past each decoded value
                break
            
            # Decode all values in the segment
            decoded = []
            idx = 0
            while idx < len(segment):
                val = 0
                shift = 0
                while idx < len(segment) and segment[idx] in _B64:
                    integer = _B64.index(segment[idx])
                    idx += 1
                    if integer & 32:
                        integer = -(integer & 31)
                    val |= (integer & 31) << shift
                    shift += 5
                    if not (integer & 32):
                        break
                decoded.append(val)
            
            if len(decoded) < 1:
                continue
            
            gen_col = prev_gen_col + decoded[0]
            if len(decoded) >= 4:
                prev_source_idx += decoded[1]
                prev_source_line += decoded[2]
                prev_source_col += decoded[3]
            
            prev_gen_col = gen_col
            
            if 0 <= prev_source_idx < len(sources):
                lookup_table[(gen_line, gen_col)] = (
                    sources[prev_source_idx],
                    prev_source_line + 1,  # 1-based
                )
        
        gen_line += 1
        prev_gen_col = 0
    
    def lookup(gen_line, gen_col):
        """Look up original source for a generated position."""
        # Try exact match first
        key = (gen_line, gen_col)
        if key in lookup_table:
            return lookup_table[key]
        
        # Try closest line match
        best = None
        for (gl, gc), (src, sl) in lookup_table.items():
            if gl <= gen_line:
                if best is None or gl > best[0]:
                    best = (gl, gc, src, sl)
        
        if best:
            return (best[2], best[3])
        
        return None
    
    return lookup
