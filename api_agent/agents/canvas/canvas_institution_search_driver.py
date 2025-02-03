import requests


def find_schools(search_term):
    """
    Query Instructure's public search endpoint to find matching schools by name.
    Returns a list of dicts, each with 'name' and 'canvas_url'.
    """
    base_url = "https://canvas.instructure.com/api/v1/accounts/search"
    params = {
        "name": search_term,
        "per_page": 50
    }

    response = requests.get(base_url, params=params)
    response.raise_for_status()  # raise an error if the request fails

    data = response.json()
    results = []
    for item in data:
        school_name = item.get('name')
        domain = item.get('domain')

        # Construct a https:// link from the domain
        if domain:
            canvas_url = f"https://{domain}"
            results.append({"name": school_name, "canvas_url": canvas_url})

    return results


def main():
    search_term = "Cha"
    schools = find_schools(search_term)
    print(f'Canvas URL results for "{search_term}":')
    for s in schools:
        print(f"- {s['name']}: {s['canvas_url']}")


if __name__ == "__main__":
    main()
