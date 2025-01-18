import requests
import os
from dotenv import load_dotenv
import json
from pathlib import Path
import yaml

load_dotenv()


def search_github_repos(keywords, token=None, min_stars=0, min_forks=0):
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

    base_url = "https://api.github.com/search/repositories"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repo_urls = {}
    for keyword in keywords:
        params = {"q": keyword}
        try:
            response = requests.get(base_url, headers=headers, params=params)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            data = response.json()
            repo_urls_for_keyword = []
            for item in data.get("items", []):
                if item["stargazers_count"] >= min_stars and item["forks_count"] >= min_forks:
                    repo_urls_for_keyword.append(item["html_url"])
            repo_urls[keyword] = repo_urls_for_keyword
        except requests.exceptions.RequestException as e:
            print(f"Error searching for '{keyword}': {e}")
            repo_urls[keyword] = []  # ensure there's always an entry even with errors

    return repo_urls


def load_existing_data(filepath):
    """Loads existing data from a JSON file.

    Args:
        filepath (str): The path to the JSON file.

    Returns:
        dict: The loaded data, or an empty dictionary if the file doesn't exist
        or there is a json exception.
    """
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Data file not found. Starting with empty results")
        return {}
    except json.JSONDecodeError:
        print("Error decoding JSON file. Starting with empty results")
        return {}


def save_data(filepath, data):
    """Saves data to a JSON file.

    Args:
        filepath (str): The path to the JSON file.
        data (dict): The data to save.
    """

    # ensure parent directory exists
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def merge_and_save_results(keywords, token, output_filepath, min_stars=0, min_forks=0):
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
        existing_urls = existing_data.get(keyword, [])  # return empty list for that key if key doesnt exists
        merged_urls = list(set(existing_urls + new_urls))  # set will ensure uniqueness.
        merged_data[keyword] = merged_urls
    # 4. save to file
    save_data(output_filepath, merged_data)
    print(f"Results saved to: {output_filepath}")


if __name__ == "__main__":
    keywords_str = os.getenv("KEYWORDS_ENV")
    if keywords_str:
        keywords_to_search = [keyword.strip() for keyword in keywords_str.split(",")]
    else:
        keywords_to_search = []
        print("No Keywords specified. Please specify via KEYWORDS_ENV")

    github_token = os.getenv("GITHUB_TOKEN")
    min_stars_filter = int(os.getenv("MIN_STARS", 20))
    min_forks_filter = int(os.getenv("MIN_FORKS", 100))

    output_file = "results/data.json"
    merge_and_save_results(
        keywords_to_search,
        github_token,
        output_file,
        min_stars_filter,
        min_forks_filter,
    )
