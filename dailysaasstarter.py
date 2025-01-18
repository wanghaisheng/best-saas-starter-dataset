import requests
import os
from dotenv import load_dotenv
import json
from pathlib import Path
import logging
import time
import yaml
import argparse
from typing import List, Dict, Any

load_dotenv()

# Constants
GITHUB_API_BASE_URL = "https://api.github.com/search/repositories"
GITHUB_API_VERSION = "2022-11-28"


def load_config(config_path: str) -> Dict:
    """Loads configuration from a YAML file.

    Args:
        config_path (str): The path to the YAML file.

    Returns:
        dict: The loaded configuration, or an empty dictionary if the file doesn't exist
        or there is a yaml exception.
    """
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.warning("Config file not found, using env variables.")
        return {}
    except yaml.YAMLError as e:
         logging.error(f"Error parsing config file {e}")
         return {}


def search_github_repos(
    keywords: List[str], token: str = None, min_stars: int = 0, min_forks: int = 0
) -> Dict[str, List[str]]:
    """
    Searches GitHub repositories for given keywords, filtering by stars and forks.

    Args:
        keywords (list): A list of keywords to search for.
        token (str, optional): A GitHub personal access token for higher rate limits. Defaults to None.
        min_stars (int, optional): Minimum number of stars a repo should have. Defaults to 0.
        min_forks (int, optional): Minimum number of forks a repo should have. Defaults to 0.

    Returns:
        dict: A dictionary where keys are keywords and values are lists of repository URLs.
             Returns empty dict if there are no results for a keyword.

    Raises:
        requests.exceptions.RequestException: If there's an error during the API request.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repo_urls = {}
    for keyword in keywords:
        params = {"q": keyword}
        try:
            all_repo_urls_for_keyword = []
            next_page_url = GITHUB_API_BASE_URL
            while next_page_url:
                logging.info(f"Searching for '{keyword}' at '{next_page_url}'")
                response = requests.get(
                    next_page_url, headers=headers, params=params
                )
                response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

                data = response.json()
                logging.debug(f"API response data: {data}")
                repo_urls_for_keyword = []
                for item in data.get("items", []):
                    if (
                        item["stargazers_count"] >= min_stars
                        and item["forks_count"] >= min_forks
                    ):
                        repo_urls_for_keyword.append(item["html_url"])
                all_repo_urls_for_keyword.extend(repo_urls_for_keyword)
                # Handle Pagination
                if "Link" in response.headers:
                    link_header = response.headers["Link"]
                    next_links = [
                        link.split(";")[0].strip("<>")
                        for link in link_header.split(",")
                        if 'rel="next"' in link
                    ]
                    next_page_url = next_links[0] if next_links else None
                else:
                    next_page_url = None

            repo_urls[keyword] = all_repo_urls_for_keyword
        except requests.exceptions.RequestException as e:
            logging.error(f"Error searching for '{keyword}': {e}")
            repo_urls[keyword] = []  # ensure there's always an entry even with errors
            time.sleep(
                60
            )  # In case of rate limit or other error, wait a minute before trying again

    return repo_urls


def load_existing_data(filepath: Path) -> Dict[str, List[str]]:
    """Loads existing data from a JSON file or returns an empty dict if the file does not exist.

    Args:
        filepath (str): The path to the JSON file.

    Returns:
        dict: The loaded data, or an empty dictionary if the file doesn't exist
        or there is a json exception.
    """
    if not filepath.exists():
        logging.info("Data file not found. Starting with empty results")
        return {}
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        logging.warning("Error decoding JSON file. Starting with empty results")
        return {}


def save_data(filepath: Path, data: Dict[str, List[str]]) -> None:
    """Saves data to a JSON file.

    Args:
        filepath (str): The path to the JSON file.
        data (dict): The data to save.
    """
    # ensure parent directory exists
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def merge_and_save_results(
    keywords: List[str],
    token: str,
    output_filepath: Path,
    min_stars: int = 0,
    min_forks: int = 0,
) -> None:
    """Searches, loads existing data, merges, and saves new data.

    Args:
       keywords (list): A list of keywords to search for.
       token (str, optional): A GitHub personal access token for higher rate limits. Defaults to None.
       output_filepath (str) : Path to save the results to
       min_stars (int, optional): Minimum number of stars a repo should have. Defaults to 0.
       min_forks (int, optional): Minimum number of forks a repo should have. Defaults to 0.
    """
    # 1. search github for keywords, with filter criteria
    new_results = search_github_repos(keywords, token, min_stars, min_forks)

    # 2. Load existing data (or initialize an empty dict)
    existing_data = load_existing_data(output_filepath)
    # 3.  Merge the data, make them unique
    merged_data = {}
    for keyword, new_urls in new_results.items():
        if not new_urls:
            logging.warning(f"No results for {keyword}. skipping...")
            continue #Skip if there are no results
        existing_urls = existing_data.get(
            keyword, []
        )  # return empty list for that key if key doesnt exists
        merged_urls = list(set(existing_urls + new_urls))  # set will ensure uniqueness.
        merged_data[keyword] = merged_urls

    # 4. save to file
    save_data(output_filepath, merged_data)
    logging.info(f"Results saved to: {output_filepath}")

def validate_config(config: Dict):
    if "min_stars" in config and not isinstance(config["min_stars"], int) or config["min_stars"] < 0:
        raise ValueError("min_stars must be a non-negative integer")
    if "min_forks" in config and not isinstance(config["min_forks"], int) or config["min_forks"] < 0:
        raise ValueError("min_forks must be a non-negative integer")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Setup argument parser
    parser = argparse.ArgumentParser(description="Search and merge GitHub repository data")
    parser.add_argument("--config", type=str, help="Path to the YAML config file.")
    args = parser.parse_args()

    # Load Configuration
    config = load_config(args.config) if args.config else {}
    validate_config(config)

    keywords_str = config.get("keywords", os.getenv("KEYWORDS_ENV"))
    if keywords_str:
        keywords_to_search = [keyword.strip() for keyword in keywords_str.split(",") if keyword.strip()]
    else:
        keywords_to_search = []
        logging.error("No Keywords specified. Please specify via KEYWORDS_ENV or in the config file.")
        exit(1)


    github_token = config.get("github_token", os.getenv("GITHUB_TOKEN"))
    min_stars_filter = config.get("min_stars", int(os.getenv("MIN_STARS", 10)))
    min_forks_filter = config.get("min_forks", int(os.getenv("MIN_FORKS", 10)))

    output_file = Path(config.get("output_file", "results/data.json"))

    merge_and_save_results(
        keywords_to_search,
        github_token,
        output_file,
        min_stars_filter,
        min_forks_filter,
    )
