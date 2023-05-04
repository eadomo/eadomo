import requests


def has_diff_between_two_branches(url, private_token, project_id, branch_dev, branch_deploy):
    headers = {"PRIVATE-TOKEN": private_token}

    resp = requests.get(f"{url}/api/v4/projects/{project_id}/repository"
                        f"/compare?from={branch_deploy}&to={branch_dev}&straight=true",
                        headers=headers, timeout=300)
    if resp.status_code == 200:
        diff = resp.json()
        num_commits = len(diff['commits'])
        return num_commits > 0

    return None
