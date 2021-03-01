import requests as req
import json
from getpass import getpass
import re
import sys

## CONFIGURATION

confluence_req_str="https://confluence.ascendntnu.no/rest/api/content"
jira_req_str="https://jira.ascendntnu.no/rest/api/2/search"

# Settings for Jira single issue macro
jira_macro_id = "5ded959b-ea64-498a-a5e9-01356e2cf51a"
server_id = "741b69ce-e911-31ef-a42f-8ada2530ac21"
server_name = "Ascend JIRA"
columns = "key,summary,type,created,updated,due,assignee,reporter,priority,status,resolution"




## HELPER FUNCTIONS

# Convert HTML character codes to normal characters
def unEscapeHTML(str):
    return str\
    	.replace("&amp", "&")\
    	.replace("&quot", "\"")\
    	.replace("&apos", "'")\
    	.replace("&gt", ">")\
    	.replace("&lt", "<")\
    	.replace(";", "")

# Parse the source XML and find all applicable JIRA widgest
def getJiraWidgetsFromPageSrc(src):
    widgets = []
    # Use regex pattern to find the start index of all JIRA widgets on the page
    widget_start = [m.start() for m in re.finditer("(<ac:structured-macro)[^>]*(ac:name=\"jira\")[^>]*>", page_content)]

    # Further process each detected JIRA widget
    for start_pos in widget_start:
        cur_widget = {}
        cur_widget["start"] = start_pos
        # Use regex pattern to find the end index for the JIRA macro
        cur_widget["stop"] = re.search("<\\/ac:structured-macro>", page_content[start_pos:]).end() + start_pos
        # Everything between the start and stop index is part of the JIRA macro
        widget_str = page_content[cur_widget["start"]:cur_widget["stop"]]
        # Try to find the start index of the widget query
        try:
            query_start = re.search("<ac:parameter ac:name=\"jqlQuery\">", widget_str).end()
        except:
            # If there is no query field, do not process the widget.
            # This likely means that it is a link to a single issue and not a list widget.
            continue
        # Find the end index of the widget query
        query_stop = re.search("<\/ac:parameter>", widget_str[query_start:]).start() + query_start
        cur_widget["query"] = unEscapeHTML(widget_str[query_start:query_stop])
        widgets.append(cur_widget)
    return widgets

# Connect to JIRA and get a list of issue keys of the issues that match the specified query
def getIssueKeysFromQuery(query):
    issue_keys = []
    parameters = {
        "jql": query,
        "expand": "renderedFields,schema,names"
    }
    api_answer = json.loads(req.get(jira_req_str, params=parameters, auth=(username, password)).text)
    for issue in api_answer["issues"]:
        print(issue["key"] + " " + issue["fields"]["summary"])
        issue_keys.append(issue["key"])
    return issue_keys
# Create a single-issue JIRA widget for the issue with the specified key
def createJiraSingleIssueWidget(issue_key):
    return f'<ac:structured-macro ac:name="jira" ac:schema-version="1" ac:macro-id="{jira_macro_id}"><ac:parameter ac:name="server">{server_name}</ac:parameter><ac:parameter ac:name="columns">{columns}</ac:parameter><ac:parameter ac:name="serverId">{server_id}</ac:parameter><ac:parameter ac:name="key">{issue_key}</ac:parameter></ac:structured-macro>'



## MAIN FUNCTION

# Ask user for credentials
print("Enter your confluence credentials.")
username = input("Confluence username? ")
password = getpass("Confluence password? ")

# Request the most recently modified pages. This will also serve as a check to see if the user is logged in
NUM_SUGGESTIONS = 10
parameters = {
    "cql":"type=page order by lastmodified desc",
    "maxResults": NUM_SUGGESTIONS,
    "expand": "version,space"
}
response = req.get(confluence_req_str + "/search", params=parameters, auth=(username, password))
if response.status_code != 200:
    print("Failed to connect to Confluence. Verify your login credentials and try again.")
    exit()
else:
    print("Successfully logged in.")
data = response.json()["results"]
print(f"\nShowing the {NUM_SUGGESTIONS} most recently modified pages.")
for i in range(0, min(NUM_SUGGESTIONS, len(data))):
    print (f"{i + 1}: \"{data[i]['title']}\" in space \"{data[i]['space']['name']}\"")

# Ask the user which page they want to modify
print(f"\nEnter a number from 1 to {NUM_SUGGESTIONS} to select one of the suggested pages.\nIf you want to select a different page, enter its page ID.")
page_id_input = input("? ")

# If a small number is entered, the user wants one of the suggested pages
try:
    if (int(page_id_input) <= NUM_SUGGESTIONS and int(page_id_input) > 0):
        # Get the page ID of the selected suggested page
        page_id_input = data[int(page_id_input)-1]["id"]
except:
    print("Invalid input. Exiting.")
    exit()

# Get page
response = req.get(confluence_req_str + "/" + page_id_input, params={"expand": "body.storage,version,space"}, auth=(username, password))

# Check if the page exists
if response.status_code == 404:
    print("Error. No page with that ID exists.")
    exit()
elif response.status_code == 401:
    print("Error. You are not authorized for this page.")
    exit()
elif response.status_code != 200:
    print("Unknown error while fetching page.")
    exit()

data = response.json()

page_title = data["title"]
page_version = data["version"]["number"]
page_id = data["id"]
page_content = data["body"]["storage"]["value"]
page_space_name = data["space"]["name"]
page_space_key = data["space"]["key"]

# Ask the user if we found the correct page
print(f"\nSelected page: \"{page_title}\" in space \"{page_space_name}\".")
correct_page = input("Is this correct? [y/n]: ")
if correct_page != "y" and correct_page != "yes":
    print("Exiting program.")
    exit()

# Create an object for each jira widget on the page
widgets = getJiraWidgetsFromPageSrc(page_content)
if len(widgets) == 0:
    print("\nNo JIRA widgets found on the specified page. Exiting.")
    exit()
print(f"\nFound {len(widgets)} JIRA widget(s) on the specified page.")

# Copy the page contents into a new string that we can modify
new_page_content = page_content

# For each widget found..
# Notice that this is done from last to first, in order to not mess opp string indices when replacing text
print("Getting details about the JIRA issues from the server.")
print("Found the following issues:")
for cur_widget in reversed(widgets):
    sys.stdout.flush()
    # ..use the REST api to get the corresponding issue ids
    cur_widget["issue_keys"] = getIssueKeysFromQuery(cur_widget["query"])
    # ..generate new XML with static issue references instead of dynamic macro
    cur_widget["new_xml"] = ""
    for issue_key in cur_widget["issue_keys"]:
        if cur_widget["new_xml"] != "":
            cur_widget["new_xml"] += ""
        cur_widget["new_xml"] += "<p>" + createJiraSingleIssueWidget(issue_key) + "</p>"
    # ..replace the old widget xml with the new xml
    new_page_content = new_page_content[:cur_widget["start"]] + cur_widget["new_xml"] + new_page_content[cur_widget["stop"]:]
print("")


# Upload new page version to Confluence
payload = {
    "id": page_id,
    "type": "page",
    "title": page_title,
    "space": {"key": page_space_key},
    "body": {
        "storage": {
            "value": new_page_content,
            "representation": "storage"
        }
     },
     "version":{
         "number": page_version + 1,
         "message": "Automatically archived Jira lists using script"
     }
}
print("Uploading modified page to Confluence.")            
response = req.put(confluence_req_str + "/" + page_id, json=payload, auth=(username, password), params={"expand": "body.storage"})
if response.ok:
    print("Page successfully updated.")
else:
    print("Unknown error while updating page")