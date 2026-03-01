#!/usr/bin/env python3
"""
docs-mcp Web UI - Flask Application

Web interface for managing doc-mcp knowledge bases and MCP server.
"""

import os
import sys
import json
import logging
import webbrowser
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, abort

try:
    from md_mcp.scanner import MarkdownScanner
    from md_mcp.chunking import MarkdownChunker
except ImportError:
    # Fallback if not installed (though it should be a dependency)
    MarkdownScanner = None
    MarkdownChunker = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

import typing

# Application state
class AppState:
    """Global application state"""
    selected_folders = []
    kb_name = ""
    kb_path = None
    kb_status = "idle"  # idle | processing | ready
    mcp_server_processes: typing.Dict[str, typing.Any] = {}
    generation_results = []
    _search_cache = {} # {kb_path: (chunks, mtime)}
    
state = AppState()


def get_config_dir():
    """Get configuration directory path"""
    return Path.home() / ".docs-mcp"


def load_state():
    """Load application state from disk"""
    config_dir = get_config_dir()
    state_file = config_dir / "web_state.json"
    
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
                state.selected_folders = data.get('selected_folders', [])
                state.kb_name = data.get('kb_name', '')
                state.kb_path = data.get('kb_path')
                state.kb_status = data.get('kb_status', 'idle')
                logger.info(f"Loaded state: {len(state.selected_folders)} folders")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")


def save_state():
    """Save application state to disk"""
    config_dir = get_config_dir()
    config_dir.mkdir(exist_ok=True)
    state_file = config_dir / "web_state.json"
    
    try:
        data = {
            'selected_folders': state.selected_folders,
            'kb_name': state.kb_name,
            'kb_path': state.kb_path,
            'kb_status': state.kb_status,
            'last_updated': datetime.now().isoformat()
        }
        
        with open(state_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info("State saved successfully")
    except Exception as e:
        logger.error(f"Failed to save state: {e}")


import importlib.metadata

def get_md_mcp_version():
    try:
        return importlib.metadata.version('md-mcp')
    except importlib.metadata.PackageNotFoundError:
        return "unknown"

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html',
                         folders=state.selected_folders,
                         kb_name=state.kb_name,
                         kb_status=state.kb_status,
                         kb_path=state.kb_path,
                         md_mcp_version=get_md_mcp_version())


@app.route('/api/folders', methods=['GET'])
def api_get_folders():
    """Get list of selected folders"""
    return jsonify({
        'success': True,
        'folders': [
            {'path': folder, 'name': os.path.basename(folder)}
            for folder in state.selected_folders
        ]
    })


@app.route('/api/folders', methods=['POST'])
def api_add_folder():
    """Add a folder to the selection"""
    try:
        data = request.get_json()
        folder_path = data.get('path', '').strip()
        
        if not folder_path:
            return jsonify({'success': False, 'message': 'No path provided'}), 400
        
        # Normalize path
        folder_path = os.path.abspath(folder_path)
        
        # Validate folder exists
        if not os.path.isdir(folder_path):
            return jsonify({'success': False, 'message': 'Path is not a directory'}), 400
        
        # Check if already added
        if folder_path in state.selected_folders:
            return jsonify({'success': False, 'message': 'Folder already added'}), 400
        
        # Add folder
        state.selected_folders.append(folder_path)
        save_state()
        
        logger.info(f"Folder added: {folder_path}")
        
        return jsonify({
            'success': True,
            'message': f'Added: {os.path.basename(folder_path)}',
            'folders': [
                {'path': f, 'name': os.path.basename(f)}
                for f in state.selected_folders
            ]
        })
    
    except Exception as e:
        logger.error(f"Error adding folder: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/folders/<int:index>', methods=['DELETE'])
def api_remove_folder(index):
    """Remove a folder from the selection"""
    try:
        if index < 0 or index >= len(state.selected_folders):
            return jsonify({'success': False, 'message': 'Invalid index'}), 400
        
        removed = state.selected_folders.pop(index)
        save_state()
        
        logger.info(f"Folder removed: {removed}")
        
        return jsonify({
            'success': True,
            'message': f'Removed: {os.path.basename(removed)}',
            'folders': [
                {'path': f, 'name': os.path.basename(f)}
                for f in state.selected_folders
            ]
        })
    
    except Exception as e:
        logger.error(f"Error removing folder: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/folders/clear', methods=['POST'])
def api_clear_folders():
    """Clear all selected folders"""
    try:
        state.selected_folders = []
        save_state()
        
        logger.info("All folders cleared")
        
        return jsonify({
            'success': True,
            'message': 'All folders cleared',
            'folders': []
        })
    
    except Exception as e:
        logger.error(f"Error clearing folders: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/browse-folder', methods=['GET'])
def api_browse_folder():
    """Open native file dialog to select a folder"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        # Create a root window and hide it
        root = tk.Tk()
        root.withdraw()
        
        # Make it appear on top of other windows
        root.attributes('-topmost', True)
        
        folder_path = filedialog.askdirectory(
            title="Select Code Folder"
        )
        
        # Destroy the root window
        root.destroy()
        
        if folder_path:
            return jsonify({
                'success': True,
                'path': folder_path
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No folder selected'
            })
            
    except Exception as e:
        logger.error(f"Error opening folder browser: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/generate', methods=['POST'])
def api_generate_kb():
    """Generate knowledge base from selected folders"""
    try:
        data = request.get_json()
        kb_name = data.get('kb_name', '').strip()
        
        if not kb_name:
            return jsonify({'success': False, 'message': 'Knowledge base name required'}), 400
        
        if not state.selected_folders:
            return jsonify({'success': False, 'message': 'No folders selected'}), 400
        
        # Update state
        state.kb_name = kb_name
        state.kb_status = "processing"
        save_state()
        
        # Run generation in background
        def generate():
            try:
                logger.info(f"Starting KB generation: {kb_name}")
                logger.info(f"Folders: {state.selected_folders}")
                
                output_dir = get_config_dir() / "kbs" / kb_name
                
                # Clear existing files in the KB directory
                import shutil
                if output_dir.exists():
                    shutil.rmtree(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                
                # Make sure all selected folders are strings
                folder_strs = [str(f) for f in state.selected_folders]
                
                # Use UTF-8 environment for Windows compatibility with emojis
                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                
                # Run repomix for each folder individually
                for folder_path in folder_strs:
                    folder_name = os.path.basename(folder_path)
                    output_file = output_dir / f"{folder_name}.md"
                    
                    cmd = ["uvx", "repomix", "--output", str(output_file), folder_path]
                    logger.info(f"Running command: {' '.join(cmd)}")
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
                    logger.info(f"repomix output for {folder_name}: {result.stdout}")
                
                # Update state
                state.kb_path = str(output_dir)
                state.kb_status = "ready"
                state.generation_results = [
                    {'folder': f, 'status': 'processed', 'files': -1} # repomix doesn't easily expose this
                    for f in state.selected_folders
                ]
                save_state()
                
                logger.info(f"KB generation completed: {kb_name}")
                
            except subprocess.CalledProcessError as e:
                logger.error(f"Error generating KB: {e.stderr}")
                state.kb_status = "idle"
                save_state()
            except Exception as e:
                logger.error(f"Error generating KB: {e}")
                state.kb_status = "idle"
                save_state()
        
        # Start background thread
        thread = threading.Thread(target=generate, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'Generating knowledge base: {kb_name}',
            'status': 'processing'
        })
    
    except Exception as e:
        logger.error(f"Error in generate endpoint: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/kb/status', methods=['GET'])
def api_kb_status():
    """Get knowledge base status"""
    return jsonify({
        'success': True,
        'status': state.kb_status,
        'kb_name': state.kb_name,
        'kb_path': state.kb_path,
        'folder_count': len(state.selected_folders),
        'results': state.generation_results
    })


@app.route('/api/kbs', methods=['GET'])
def api_list_kbs():
    """List all available knowledge bases"""
    try:
        kbs_dir = get_config_dir() / "kbs"
        kbs = []
        
        if kbs_dir.exists():
            for d in kbs_dir.iterdir():
                if d.is_dir():
                    # Check if server is running
                    is_running = d.name in state.mcp_server_processes
                    
                    kbs.append({
                        'name': d.name,
                        'path': str(d),
                        'modified': d.stat().st_mtime,
                        'running': is_running
                    })
        
        # Sort by modification time, newest first
        kbs.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'success': True,
            'kbs': kbs
        })
    except Exception as e:
        logger.error(f"Error listing KBs: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/kbs/<kb_name>', methods=['DELETE'])
def api_remove_kb(kb_name):
    """Remove a knowledge base"""
    try:
        # Stop server if running
        if kb_name in state.mcp_server_processes:
            process = state.mcp_server_processes[kb_name]
            process.terminate()
            state.mcp_server_processes.pop(kb_name, None)
            logger.info(f"Stopped server for {kb_name}")
            
        # Try to remove from Claude Desktop config
        try:
            cmd = ["uvx", "md-mcp", "--remove", kb_name]
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            subprocess.run(cmd, env=env, capture_output=True, check=False)
            logger.info(f"Removed Claude Desktop config for {kb_name}")
        except Exception as e:
            logger.error(f"Failed to remove Claude Desktop config: {e}")
            
        # Delete directory
        kb_path = get_config_dir() / "kbs" / kb_name
        if kb_path.exists():
            import shutil
            shutil.rmtree(kb_path)
            logger.info(f"Deleted KB directory: {kb_path}")
            
        return jsonify({
            'success': True,
            'message': f'Knowledge base {kb_name} removed'
        })
    except Exception as e:
        logger.error(f"Error removing KB {kb_name}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/server/start', methods=['POST'])
def api_start_server():
    """Start MCP server"""
    try:
        data = request.get_json() or {}
        kb_name = data.get('kb_name')
        
        if not kb_name:
            return jsonify({'success': False, 'message': 'kb_name is required'}), 400
            
        if kb_name in state.mcp_server_processes:
            return jsonify({
                'success': False,
                'message': 'Server is already running for this KB'
            }), 400
        
        kb_path = get_config_dir() / "kbs" / kb_name
        if not kb_path.exists():
            return jsonify({
                'success': False,
                'message': 'Knowledge base directory not found.'
            }), 404
        
        logger.info(f"Starting MCP server for KB: {kb_path}")
                
        cmd = ["uvx", "md-mcp", "--folder", str(kb_path)]
        
        # Use UTF-8 environment for Windows compatibility
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        
        process = subprocess.Popen(cmd, env=env)
        state.mcp_server_processes[kb_name] = process
        
        return jsonify({
            'success': True,
            'message': 'MCP server started',
            'config': get_mcp_config(kb_name, str(kb_path))
        })
    
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/server/stop', methods=['POST'])
def api_stop_server():
    """Stop MCP server"""
    try:
        data = request.get_json() or {}
        kb_name = data.get('kb_name')
        
        if not kb_name:
            return jsonify({'success': False, 'message': 'kb_name is required'}), 400
            
        if kb_name not in state.mcp_server_processes:
            return jsonify({
                'success': False,
                'message': 'Server is not running for this KB'
            }), 400
            
        process = state.mcp_server_processes[kb_name]
        process.terminate()
        state.mcp_server_processes.pop(kb_name, None)
        
        logger.info(f"MCP server stopped for {kb_name}")
        
        # Try to remove from Claude Desktop config
        try:
            cmd = ["uvx", "md-mcp", "--remove", kb_name]
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            subprocess.run(cmd, env=env, capture_output=True, check=False)
            logger.info(f"Removed Claude Desktop config for {kb_name}")
        except Exception as e:
            logger.error(f"Failed to remove Claude Desktop config: {e}")
        
        return jsonify({
            'success': True,
            'message': 'MCP server stopped'
        })
    
    except Exception as e:
        logger.error(f"Error stopping server: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/server/status', methods=['GET'])
def api_server_status():
    """Get all MCP servers status"""
    configs = {}
    for kb_name in state.mcp_server_processes.keys():
        kb_path = str(get_config_dir() / "kbs" / kb_name)
        configs[kb_name] = get_mcp_config(kb_name, kb_path)
        
    return jsonify({
        'success': True,
        'running_servers': list(state.mcp_server_processes.keys()),
        'configs': configs
    })


@app.route('/api/search', methods=['POST'])
def api_search():
    """Test search in knowledge base"""
    try:
        if state.kb_status != "ready" or not state.kb_path:
            return jsonify({
                'success': False,
                'message': 'No knowledge base available'
            }), 400
        
        data = request.get_json()
        query = data.get('query', '').strip()
        
        if not query:
            return jsonify({'success': False, 'message': 'Query required'}), 400
        
        if not MarkdownScanner or not MarkdownChunker:
            return jsonify({
                'success': False,
                'message': 'md-mcp library not found. Search unavailable.'
            }), 500

        if not state.kb_path:
            return jsonify({
                'success': False,
                'message': 'Knowledge base path not set'
            }), 400

        kb_path = Path(state.kb_path)
        
        # Get all markdown files and chunk them
        # Use cache if available and directory hasn't changed
        current_mtime = kb_path.stat().st_mtime
        cache_entry = state._search_cache.get(str(kb_path))
        
        if cache_entry and cache_entry[1] == current_mtime:
            chunks = cache_entry[0]
        else:
            logger.info(f"Building search index for {kb_path}...")
            scanner = MarkdownScanner(str(kb_path))
            chunker = MarkdownChunker()
            
            files = scanner.scan()
            chunks = []
            for f in files:
                f.load()
                chunks.extend(chunker.chunk_markdown(f.content, file_path=f.relative_path))
            
            state._search_cache[str(kb_path)] = (chunks, current_mtime)
            logger.info(f"Built index with {len(chunks)} chunks")

        # Perform search
        chunker = MarkdownChunker()
        snippets = chunker.search_chunks(chunks, query, max_results=5)
        
        results = [
            {
                'file': str(s.file_path) if s.file_path else "",
                'score': float(s.match_score),
                'snippet': s.snippet,
                'header': str(s.header_path) if s.header_path else "Root"
            }
            for s in snippets
        ]
        
        return jsonify({
            'success': True,
            'query': query,
            'results': results
        })
    
    except Exception as e:
        logger.error(f"Error in search: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


def get_mcp_config(kb_name, kb_path):
    """Generate MCP server configuration snippet for Claude Desktop"""
    return {
        'mcpServers': {
            kb_name: {
                'command': 'uvx',
                'args': ['md-mcp', '--folder', kb_path]
            }
        }
    }


def start_web_server(port=5000, host='127.0.0.1', open_browser=True):
    """Start the Flask web server"""
    url = f"http://{host}:{port}"
    
    print("\n" + "="*60)
    print(f"docs-mcp Web UI Started!")
    print("="*60)
    print(f"URL: {url}")
    print(f"Configuration: {get_config_dir()}")
    print("="*60)
    print("\nTo stop the server, press Ctrl+C")
    print("="*60 + "\n")
    
    # Open browser
    if open_browser:
        try:
            threading.Timer(1.5, lambda: webbrowser.open(url)).start()
        except:
            pass
    
    # Load state
    load_state()
    
    # Start Flask
    app.run(host=host, port=port, debug=False, threaded=True)


def main():
    """Main entry point for web UI"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='docs-mcp Web UI',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--port', '-p', type=int, default=5000,
                       help='Port to run web server on (default: 5000)')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                       help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--no-browser', action='store_true',
                       help='Do not open browser automatically')
    
    args = parser.parse_args()
    
    try:
        start_web_server(
            port=args.port,
            host=args.host,
            open_browser=not args.no_browser
        )
    except KeyboardInterrupt:
        print("\n\nServer stopped.")
    except Exception as e:
        logger.error(f"Error starting server: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
