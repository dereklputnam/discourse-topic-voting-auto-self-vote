# Backfill Self-Votes Script for Discourse Topic Voting
#
# This script adds votes for topic authors who haven't voted on their own topics
# in voting-enabled categories.
#
# Usage:
#   1. SSH into your Discourse server
#   2. cd /var/discourse
#   3. ./launcher enter app
#   4. rails c
#   5. Paste this script or load it with: load '/path/to/backfill_self_votes.rb'
#
# Configuration options are at the top of the script.

#==============================================================================
# CONFIGURATION
#==============================================================================

# Set to false to actually create votes (true = preview only)
DRY_RUN = true

# Limit to specific category IDs (empty array = all voting-enabled categories)
# Example: [89, 90, 91]
CATEGORY_IDS = []

# Exclude users in these group IDs from backfill
# Example: [1, 2, 3]
EXCLUDED_GROUP_IDS = []

#==============================================================================
# SCRIPT
#==============================================================================

puts "\n#{'=' * 60}"
puts "Backfill Self-Votes Script"
puts "#{'=' * 60}"
puts "Mode: #{DRY_RUN ? 'DRY RUN (no changes)' : 'LIVE (votes will be created)'}"
puts "#{'=' * 60}\n\n"

# Verify Topic Voting plugin is installed
unless defined?(DiscourseTopicVoting)
  puts "ERROR: Topic Voting plugin not found!"
  puts "This script requires the discourse-topic-voting plugin."
  return
end

# Get voting-enabled category IDs
if CATEGORY_IDS.empty?
  voting_category_ids = CategoryCustomField
    .where(name: 'enable_topic_voting', value: 'true')
    .pluck(:category_id)
else
  voting_category_ids = CATEGORY_IDS
end

if voting_category_ids.empty?
  puts "ERROR: No voting-enabled categories found!"
  return
end

puts "Voting-enabled categories: #{voting_category_ids.join(', ')}"

# Get excluded user IDs
excluded_user_ids = Set.new
if EXCLUDED_GROUP_IDS.any?
  excluded_user_ids = GroupUser.where(group_id: EXCLUDED_GROUP_IDS).pluck(:user_id).to_set
  puts "Excluding #{excluded_user_ids.count} users in groups: #{EXCLUDED_GROUP_IDS.join(', ')}"
end

puts "\nSearching for topics where authors haven't self-voted...\n\n"

# Find topics needing votes using a more efficient query
# The plugin stores votes in the discourse_topic_voting_votes table
topics_without_self_vote = Topic
  .joins("LEFT JOIN discourse_topic_voting_votes ON discourse_topic_voting_votes.topic_id = topics.id AND discourse_topic_voting_votes.user_id = topics.user_id")
  .where(category_id: voting_category_ids)
  .where(deleted_at: nil)
  .where("discourse_topic_voting_votes.id IS NULL")

if excluded_user_ids.any?
  topics_without_self_vote = topics_without_self_vote.where.not(user_id: excluded_user_ids.to_a)
end

topics_to_process = topics_without_self_vote.includes(:user).to_a

puts "Found #{topics_to_process.count} topics where authors haven't voted\n\n"

if topics_to_process.empty?
  puts "Nothing to do - all topic authors have already voted!"
  return
end

# Process each topic
votes_created = 0
errors = []

topics_to_process.each_with_index do |topic, index|
  author = topic.user

  if author.nil?
    errors << { topic_id: topic.id, error: "Author not found" }
    next
  end

  print "[#{index + 1}/#{topics_to_process.count}] Topic ##{topic.id} \"#{topic.title.truncate(40)}\" by @#{author.username}"

  if DRY_RUN
    puts " -> would vote"
    votes_created += 1
  else
    begin
      # Use the plugin's Vote model to create the vote
      DiscourseTopicVoting::Vote.create!(
        topic_id: topic.id,
        user_id: author.id
      )

      # Update the cached vote count on the topic
      new_count = DiscourseTopicVoting::Vote.where(topic_id: topic.id).count
      topic.custom_fields[DiscourseTopicVoting::VOTE_COUNT] = new_count
      topic.save_custom_fields(true)

      puts " -> voted!"
      votes_created += 1
    rescue ActiveRecord::RecordNotUnique
      # Vote already exists (race condition or data inconsistency)
      puts " -> already voted (skipped)"
    rescue => e
      errors << { topic_id: topic.id, error: e.message }
      puts " -> ERROR: #{e.message}"
    end
  end
end

puts "\n#{'=' * 60}"
puts "SUMMARY"
puts "#{'=' * 60}"
puts "Topics found: #{topics_to_process.count}"
puts "Votes #{DRY_RUN ? 'to create' : 'created'}: #{votes_created}"
puts "Errors: #{errors.count}"

if errors.any?
  puts "\nErrors encountered:"
  errors.each { |e| puts "  - Topic ##{e[:topic_id]}: #{e[:error]}" }
end

if DRY_RUN
  puts "\n** DRY RUN COMPLETE **"
  puts "To create votes, set DRY_RUN = false and run again."
end

puts ""
