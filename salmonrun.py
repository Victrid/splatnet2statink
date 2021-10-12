# eli fessler
from __future__ import print_function
from builtins import input
import requests, json, uuid
import dbs

version = "unknown"
cookie = ""
api_key = ""
app_head = {}

def boss_kills(killed):
    boss_map = {
            "goldie":    3,
            "steelhead": 6,
            "flyfish":   9,
            "scrapper":  12,
            "steel_eel": 13,
            "stinger":   14,
            "maws":      15,
            "griller":   16,
            "drizzler":  21
            }
    return {key:killed(value) for key, value in boss_map.items()}


def salmon_load_json():
	'''Returns Salmon Run summary JSON from online.'''

	print("Pulling Salmon Run data from online...")
	url = "https://app.splatoon2.nintendo.net/api/coop_results"
	results_list = requests.get(url, headers=app_head, cookies=dict(iksm_session=cookie))
	return json.loads(results_list.text)

def salmon_post_profile(profile):
	''' Updates stat.ink Salmon Run stats/profile.'''

	payload = {
		"work_count":        profile["card"]["job_num"],
		"total_golden_eggs": profile["card"]["golden_ikura_total"],
		"total_eggs":        profile["card"]["ikura_total"],
		"total_rescued":     profile["card"]["help_total"],
		"total_point":       profile["card"]["kuma_point_total"]
	}

	url  = 'https://stat.ink/api/v2/salmon-stats'
	auth = {'Authorization': 'Bearer {}'.format(api_key)}
	updateprofile = requests.post(url, headers=auth, data=payload)

	if updateprofile.ok:
		print("Successfully updated your Salmon Run profile.")
	else:
		print("Could not update your Salmon Run profile. Error from stat.ink:")
		print(updateprofile.text)

def set_teammates(payload, job_id):
	'''Returns a new payload with the teammates key present.'''

	url = "https://app.splatoon2.nintendo.net/api/coop_results/{}".format(job_id)
	job = requests.get(url, headers=app_head, cookies=dict(iksm_session=cookie))
	results = json.loads(job.text)

	try:
		results["other_results"] # only present in shift jsons
	except KeyError:
		print("Problem retrieving shift details. Continuing without teammates' scoreboard statistics.")
		return payload # same payload as passed in, no modifications

	translate_specials = {2: 'pitcher', 7: 'presser', 8: 'jetpack', 9: 'chakuchi'}
        payload["teammates"]=[ {
            # Principal ID & nickname
            "splatnet_id":              result["pid"],
            "name":                     result["name"],

            # Special weapon
            "special":                  translate_specials[int(result["special"]["id"])],

            # Rescues, deaths, egg stats
            "rescue":                   result["help_count"],
            "death":                    result["dead_count"],
            "golden_egg_delivered":     result["golden_ikura"],
            "power_egg_collected":      result["ikura_num"],

            # Special uses, main weapon
            "special_uses":             result["special_counts"],
            "weapons":                  [dbs.weapons.get(int(d["id"]),None) for d in result["weapon_list"]],

            # Boss kills
            "boss_kills":               boss_kills(lambda value: result["boss_kill_counts"][str(value)]["count"])
            } for result in results["other_results"]]

	return payload # return modified payload w/ teammates key

def stat_ink_UUID(job_id, principal_id):
        namespace = uuid.UUID(u'{418fe150-cb33-11e8-8816-d050998473ba}')
        name = "{}@{}".format()
        return str(uuid.uuid5(namespace, name))
 
def salmon_post_shift(i, results):
	'''Uploads shift #i from the provided results dictionary.'''

	payload = {'agent': 'splatnet2statink', 'agent_version': version, 'automated': 'yes'}

	################
	# PAYLOAD ROOT #
	################
	job_id = results[i]["job_id"]
	payload["splatnet_number"] = job_id

	# stat.ink UUID
	principal_id = results[i]["my_result"]["pid"]
	payload["uuid"] = stat_ink_UUID(job_id, principal_id)

	# Title
	title_num = int(results[i]["grade"]["id"])
	translate_titles = {5: 'profreshional', 4: 'overachiever', 3: 'go_getter', 2: 'part_timer', 1: 'apprentice'}
	payload["title_after"] = translate_titles[title_num]

	title_exp_after = results[i]["grade_point"]
	title_exp_delta = results[i]["grade_point_delta"] # positive for win, negative for loss
	title_exp = title_exp_after - title_exp_delta
	payload["title_exp_after"] = title_exp_after
	payload["title_exp"] = title_exp

	if title_exp_after == 40 and title_exp_delta == 20:
		pass # could be legit clear 20->40, or could be rank up ?->40
	elif title_exp_after == 40 and title_exp_delta < 0 and title_num != 5:
		pass # could be legit wave 1 fail 60->40, or could be rank down ?->40; not always -20 for loss
	elif title_exp_after == 999:
		pass # ? -> 999; not always 20 for gain
	else: # rank/title did not change
		payload["title"] = translate_titles[title_num]

	# Stage
	stage_img_url = results[i]["schedule"]["stage"]["image"]
	if "6d68f5baa75f3a94e5e9bfb89b82e7377e3ecd2c" in stage_img_url:
		payload["stage"] = "shaketoba"
	elif "e07d73b7d9f0c64e552b34a2e6c29b8564c63388" in stage_img_url:
		payload["stage"] = "donburako"
	elif "e9f7c7b35e6d46778cd3cbc0d89bd7e1bc3be493" in stage_img_url:
		payload["stage"] = "tokishirazu"
	elif "65c68c6f0641cc5654434b78a6f10b0ad32ccdee" in stage_img_url:
		payload["stage"] = "dam"
	elif "50064ec6e97aac91e70df5fc2cfecf61ad8615fd" in stage_img_url:
		payload["stage"] = "polaris"

	# Hazard level
	payload["danger_rate"] = results[i]["danger_rate"]

	# Boss appearances/count
        payload["boss_appearances"] = boss_kill(lambda value:results[i]["boss_counts"][str(value)][count])

	# Number of waves played
	num_waves = len(results[i]["wave_details"])
	cleared = results[i]["job_result"]["is_clear"]
	payload["clear_waves"] = 3 if cleared else num_waves - 1
	payload["fail_reason"] = results[i]["job_result"]["failure_reason"]

	# Time
	payload["shift_start_at"] = results[i]["start_time"] # rotation start time
	payload["start_at"]       = results[i]["play_time"] # job/shift start time

	##############
	# WAVES LIST #
	##############
	payload["waves"] = []
	for wave in range(num_waves):
		payload["waves"].append({})

		# Known Occurrence
		# cohock_charge, fog, goldie_seeking, griller, mothership, rush
		event = results[i]["wave_details"][wave]["event_type"]["key"].replace("the-", "", 1).replace("-", "_")
		if event != "water_levels":
			payload["waves"][wave]["known_occurrence"] = event

		# Water level
		payload["waves"][wave]["water_level"] = results[i]["wave_details"][wave]["water_level"]["key"] # low, normal, high

		# Eggs
		payload["waves"][wave]["golden_egg_quota"]       = results[i]["wave_details"][wave]["quota_num"]
		payload["waves"][wave]["golden_egg_appearances"] = results[i]["wave_details"][wave]["golden_ikura_pop_num"]
		payload["waves"][wave]["golden_egg_delivered"]   = results[i]["wave_details"][wave]["golden_ikura_num"]
		payload["waves"][wave]["power_egg_collected"]    = results[i]["wave_details"][wave]["ikura_num"]

	#################
	# PLAYER'S DATA #
	#################
	payload["my_data"] = {}

	# Principal ID & nickname
	payload["my_data"]["splatnet_id"] = principal_id
	payload["my_data"]["name"]        = results[i]["my_result"]["name"]

	# Special weapon
	translate_specials = {2: 'pitcher', 7: 'presser', 8: 'jetpack', 9: 'chakuchi'}
	payload["my_data"]["special"] = translate_specials[int(results[i]["my_result"]["special"]["id"])]

	# Rescues, deaths, egg stats
	payload["my_data"]["rescue"]               = results[i]["my_result"]["help_count"]
	payload["my_data"]["death"]                = results[i]["my_result"]["dead_count"]
	payload["my_data"]["golden_egg_delivered"] = results[i]["my_result"]["golden_ikura_num"]
	payload["my_data"]["power_egg_collected"]  = results[i]["my_result"]["ikura_num"]

	# Species, gender
	payload["my_data"]["species"] = results[i]["player_type"]["species"][:-1] # inklings -> inkling
	payload["my_data"]["gender"]  = results[i]["player_type"]["style"]

	# Special uses, main weapon
	weapon_list = results[i]["my_result"]["weapon_list"]
	payload["my_data"]["special_uses"] = results[i]["my_result"]["special_counts"] # list
	payload["my_data"]["weapons"]      = [dbs.weapons.get(int(d["id"]), None) for d in weapon_list]

	# Boss kills
        payload["my_data"]["boss_kills"] = boss_kills(lambda value:results[i]["my_result"]["boss_kill_counts"][str(value)]["count"])

	#########################
	# TEAMMATES LIST & DATA #
	#########################
	payload = set_teammates(payload, job_id)

	#************
	#*** POST ***
	#************
	url  = 'https://stat.ink/api/v2/salmon'
	auth = {'Authorization': 'Bearer {}'.format(api_key), 'Content-Type': 'application/json'}
	postshift = requests.post(url, headers=auth, data=json.dumps(payload), allow_redirects=False)

	# Response
	headerloc = postshift.headers.get('location')
	if headerloc != None:
		if postshift.status_code == 302: # receive redirect
			print("Shift #{} already uploaded to {}".format(i+1, headerloc))
			# continue trying to upload remaining
		else: # http status code should be OK (200)
			print("Shift #{} uploaded to {}".format(i+1, headerloc))
	else: # error of some sort
		print("Error uploading shift #{}. Message from server:".format(i+1))
		print(postshift.content.decode("utf-8"))
		if i != 0: # don't prompt for final shift
			cont = input('Continue? [Y/n] ')
			if cont[0].lower() == "n":
				print("Exiting.")
				exit(1)

def salmon_get_data():
	'''Retrieves JSON data from SplatNet.'''

	data = salmon_load_json()
	if cookie == "" or "code" in data:
		print("Blank or invalid cookie. Please run splatnet2statink in non-Salmon Run mode to obtain a cookie.")
		exit(1)

	try:
		profile = data["summary"]
		results = data["results"]
	except KeyError:
		print("Error reading JSON from online.")
		exit(1)

	return profile, results

def salmon_get_num_shifts(results):
	'''Prompts user to upload a certain number of recent shifts.'''

	try:
		n = int(input("Number of recent Salmon Run shifts to upload (0-50)? "))
	except ValueError:
		print("Please enter an integer between 0 and 50. Exiting.")
		exit(0)
	if n < 1:
		print("Exiting without uploading any shifts.")
		exit(0)
	elif n > 50:
		print("SplatNet 2 only stores the 50 most recent shifts. Exiting.")
		exit(1)

	if len(results) == 0:
		print("You do not have any Salmon Run shifts recorded on SplatNet 2. Exiting.")
		exit(1)
	elif n > len(results):
		print("You do not have {} Salmon Run shifts recorded on SplatNet 2. Uploading all {}.".format(n, len(results)))
		n = len(results)

	return n

def get_statink_shifts(api_key):
	'''Returns the 100 most recently-uploaded Salmon Run shifts from stat.ink.'''

	print("Checking if there are previously-unuploaded shifts...")
	url  = 'https://stat.ink/api/v2/user-salmon?only=splatnet_number&count=100'
	auth = {'Authorization': 'Bearer {}'.format(api_key)}
	resp = requests.get(url, headers=auth)
	statink_shifts = json.loads(resp.text)
	return statink_shifts

def upload_salmon_run(s2s_version, s2s_cookie, s2s_api_key, s2s_app_head, r_flag):
	'''Main process for uploading Salmon Run shifts.'''

	global version
	version = s2s_version
	global cookie
	cookie = s2s_cookie
	global api_key
	api_key = s2s_api_key
	global app_head
	app_head = s2s_app_head

	profile, results = salmon_get_data()
	salmon_post_profile(profile)

	if r_flag: # upload all unuploaded shifts
		statink_shifts = get_statink_shifts(s2s_api_key)
		new_results = list(filter(lambda r: not(r["job_id"] in statink_shifts), results))
		unup_shifts = len(new_results)
		if unup_shifts > 0:
			print("Previously-unuploaded shifts detected. Uploading now...")
			for i in reversed(range(unup_shifts)):
				salmon_post_shift(i, new_results)
		else:
			print("No previously-unuploaded shifts found.")
	else: # manually upload a number of shifts
		n = salmon_get_num_shifts(results)
		for i in reversed(range(n)):
			salmon_post_shift(i, results)
