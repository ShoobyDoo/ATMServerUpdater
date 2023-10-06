# Script:       All the Mods - Server Updater
# Author:       ShoobyDoo 
# Date:         10/01/2023
# Description:  This script will help you update your ATM server. 
#               Currently only tested with ATM9, though I've tried to make it as modular as possible.

import os
import math
import json
import glob
import logging
import urllib.request
from zipfile import ZipFile
from datetime import datetime

__version__ = "0.1.0"

class Endpoint:
    FILES = "files"
    ADDITIONAL_FILES = "additional-files"
    DOWNLOAD = "download"


class Release:
    def __init__(self, data: dict) -> None:
        self.data = data
        
        self.id: int = data["id"]
        self.date_created: str = data["dateCreated"]
        self.date_modified: str = data["dateModified"]
        self.display_name: str = data["displayName"]
        self.file_length: int = data["fileLength"]
        self.file_name: str = data["fileName"]
        self.status: int = data["status"]
        self.game_versions: list[str] = data["gameVersions"]
        self.game_version_type_ids: list[int] = data["gameVersionTypeIds"]
        self.release_type: int = data["releaseType"]
        self.total_downloads: int = data["totalDownloads"]
        self.user: dict = data["user"]
        self.additional_files_count: int = data["additionalFilesCount"]
        self.has_server_pack: bool = data["hasServerPack"]
        self.additional_server_pack_files_count: int = data["additionalServerPackFilesCount"]
        self.is_early_access_content: bool = data["isEarlyAccessContent"]


class ATMServerUpdater:
    def __init__(self) -> None:
        print(f"-> ATMServerUpdater v{__version__} initializing...")
        
        self.CURSEFORGE_API = "https://www.curseforge.com/api/v1"
        self.prev_time = 0
        
        # ===== LOGGER SETUP START =====        
        if not os.path.exists('./logs'):
            os.mkdir('./logs')
            
        logging.basicConfig(
            filename=f'./logs/atmsu_{datetime.now().strftime("%Y-%m-%d")}.log',
            filemode='a+', 
            format='[%(asctime)s][%(name)-22s][%(levelname)-7s] : %(message)s', 
            datefmt='%d-%b-%y %H:%M:%S',
            level=logging.INFO
        )
        
        logging.root.name = 'ATMSU'
        # ===== LOGGER SETUP END =====
        
        # allow the user to interact with the logger
        self.logger = logging.getLogger("ATMServerUpdater")
        
        if os.path.isfile("config.json"): 
            print("-> Loading config...")
            config = self.read_config()
            print(f"-> Config loaded. ({len(config)} keys)")
                
        else:
            print("-> Config not found, creating...")
            with open("config.json", "w") as f:
                f.write(json.dumps({
                    "all_the_mods_9": "715572",
                    "page_index": 0,
                    "page_size": 1,
                    "sort": "dateCreated",
                    "sort_desc": "true",
                    "remove_alphas": "true",
                    "current_version": None,
                    "data": None
                }, indent=4)) 
                
            print(f"-> Config created! See './config.json' for more info.")
            self.read_config()
        
        print("-" * 40)
    
    
    def build_query_url(self, endpoint: Endpoint = Endpoint.FILES) -> str:
        return f"{self.CURSEFORGE_API}/mods/{self.all_the_mods_9}/{endpoint}?index={self.page_index}&pageSize={self.page_size}&sort={self.sort}&sortDescending={self.sort_desc}&removeAlphas={self.remove_alphas}"
    
    
    def build_download_url(self, release: Release) -> str:
        return f"{self.CURSEFORGE_API}/mods/{self.all_the_mods_9}/{Endpoint.FILES}/{release.id}/{Endpoint.DOWNLOAD}"
    
    
    def build_additional_files_url(self, release: Release) -> str:
        return f"{self.CURSEFORGE_API}/mods/{self.all_the_mods_9}/{Endpoint.FILES}/{release.id}/{Endpoint.ADDITIONAL_FILES}"
    
    
    def has_server_files(self, release: Release) -> bool:
        return release.additional_files_count > 0 and release.has_server_pack
    
    
    def get_latest_version(self) -> Release:
        print("-> Getting latest version...")
        return Release(dict(json.loads(urllib.request.urlopen(self.build_query_url()).read()))["data"][0])
    
    
    def parse_version(self, release: Release) -> str:
        return release.display_name.split("-")[-1]
    
    
    def convert_size(self, size_bytes, rounded: bool = False):
        if size_bytes == 0:
            return "0 B"
        
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p) if rounded else round(size_bytes / p, 2)
        
        return f"{s} {size_name[i]}"
    

    def download_progress_hook(self, block_count, block_size, total_size):
        if block_count * block_size > 1024:
            percent = int(block_count * block_size * 100 / total_size)
            rjf = 24  # right just factor
            statuses = ["[Aaand We're Off]".ljust(rjf), "[Getting There...]".ljust(rjf), "[Halfway Point]".ljust(rjf), "[Almost...]".ljust(rjf), "[Just A Little More...]".ljust(rjf), "[Complete]".ljust(rjf)]
            
            if percent >= 0:    status = statuses[0]
            if percent >= 20:   status = statuses[1]
            if percent >= 50:   status = statuses[2]
            if percent >= 75:   status = statuses[3]
            if percent >= 90:   status = statuses[4]
            if percent == 100:  status = statuses[5]
            
            dl_total = self.convert_size(total_size, True)
            dl_digits = len(dl_total.split(' ')[0])
            
            curr_dled_padded = f"{self.convert_size(block_count * block_size, True).split(' ')[0]:>{dl_digits}} {dl_total.split(' ')[1]}"
            
            # Create a progress bar with a fixed width (e.g., 40 characters)
            bar_width = 40
            num_blocks = int(bar_width * min(100, percent) / 100)
            bar = "[" + "█" * num_blocks + " " * (bar_width - num_blocks) + "]"
            
            print(f"-> Downloading {self.dph_filename} | Progress: {str(percent):>{2}}% {bar} {curr_dled_padded[:dl_digits + 3]} / {dl_total} | Status: {status}", end='\r')
            
    
    def get_server_files(self, release: Release) -> None:
        additional_files_url = self.build_additional_files_url(release)
        self.logger.info(f"Querying additional-files endpoint: {additional_files_url}")
        
        server_files = Release(json.loads(urllib.request.urlopen(self.build_additional_files_url(release)).read())["data"][0])
        self.logger.info(f"Additional file(s) for {release.display_name}: {server_files.data}")
        
        self.dph_filename = server_files.file_name
        urllib.request.urlretrieve(self.build_download_url(server_files), server_files.file_name, self.download_progress_hook)
        
    
    def yes_no(self, question: str) -> bool:
        while True:
            yn = input(f"{question} | (Y)es/(N)o: ")
            if yn.lower() in ["y", "yes", "n", "no"]: 
                break
            
        return yn.lower() in ["y", "yes"]
    
    
    def read_config(self, path: str = "./config.json") -> dict:
        with open(path) as f:
            config = json.loads(f.read())
            self.all_the_mods_9 = config["all_the_mods_9"]
            self.page_index = config["page_index"]
            self.page_size = config["page_size"]
            self.sort = config["sort"]
            self.sort_desc = config["sort_desc"]
            self.remove_alphas = config["remove_alphas"]
            self.data = config["data"]
            self.current_version = config["current_version"]

            self.logger.info(f"Config read ({len(config)} keys): {config}")
            return config
    
    
    def save_config(self):
        print("-> Saving config...")
        with open("config.json", "w") as f:
            f.write(json.dumps({
                "all_the_mods_9": self.all_the_mods_9,
                "page_index": self.page_index,
                "page_size": self.page_size,
                "sort": self.sort,
                "sort_desc": self.sort_desc,
                "remove_alphas": self.remove_alphas,
                "current_version": self.current_version,
                "data": self.data
            }, indent=4)) 
            
        print(f"-> Config saved!")
    
    
    def find_modpack_directories(self, curr_dir = None) -> list[str]:
        modpack_directories = []

        curr_dir = curr_dir if curr_dir != None else os.getcwd()
        # List all files and directories in the current working directory
        entries = os.listdir(curr_dir)

        # Iterate through the entries to find directories that might contain modpack server files
        for entry in entries:
            entry_path = os.path.join(curr_dir, entry)

            # Check if the entry is a directory
            if os.path.isdir(entry_path):
                print(os.listdir(entry_path))
                # Check if the directory contains certain files that indicate it's a modpack server directory
                if any(file in os.listdir(entry_path) for file in ["forge.jar", "server.properties", "mods"]):
                    modpack_directories.append(entry_path)

        return modpack_directories
    
    
    def install_update(self, filename: str) -> None:
        print("-> Installing update...")
        
        # first figure out how many server installs are present in the current directory
        print(self.find_modpack_directories())
        
        with ZipFile(filename, 'r') as zipObj:
            zipObj.extractall()
            
        print("-> Update installed!")
    
    
    def update(self):
        print("-> Update started...")
        
        latest_release: Release = self.get_latest_version()
        latest_version = self.parse_version(latest_release)
        
        if self.current_version == None:
            self.current_version = input("-> Please provide your current server files version. Example(s): \"latest\", \"0.1.12\"\n" \
                                         "   Enter version: ")
            
        if self.current_version != latest_version and self.has_server_files(latest_release):
            print(f"-> New version found! ({latest_version})")
            
            if self.yes_no("-> Do you want to update?"):
                # download the server files
                # self.get_server_files(latest_release)
                
                self.dph_filename = "Server-Files-0.1.12.zip"
                # check for existing server files, stage them in a seperate directory for upgrade without touching original files
                self.install_update(self.dph_filename)
                
                
                
                
                
                
                print("-> Update complete!")
                
            else:
                print("-> Update cancelled.")
                
        elif self.current_version == latest_version:
            print("-> You are on the latest version.")
        
        elif not self.has_server_files(latest_release):
            print("-> No server files found.")
            
        else:
            print("-> No new version found.")
        
        # save the config
        self.save_config()
