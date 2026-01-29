// Auto Vote Own Topic v1.3 - with appEvents for smooth UI update
import { apiInitializer } from "discourse/lib/api";
import { ajax } from "discourse/lib/ajax";

export default apiInitializer("1.0", (api) => {
  const currentUser = api.getCurrentUser();

  if (!currentUser) {
    return;
  }

  const log = (...args) => {
    if (settings.auto_vote_debug_mode) {
      console.log("[Auto Vote Own Topic]", ...args);
    }
  };

  log("Initializing auto-vote component for user:", currentUser.username);

  const autoVotedTopics = new Set();

  const isCategoryAllowed = (categoryId) => {
    if (!settings.auto_vote_categories || settings.auto_vote_categories.length === 0) {
      log("No category restriction configured, allowing all categories");
      return true;
    }

    const categorySettings = settings.auto_vote_categories.split("|").map((s) => s.trim()).filter(Boolean);

    if (categorySettings.length === 0) {
      log("Empty category list after parsing, allowing all categories");
      return true;
    }

    // First try: direct numeric ID match
    const numericIds = categorySettings.map((id) => parseInt(id, 10)).filter((id) => !isNaN(id));
    if (numericIds.length > 0 && numericIds.includes(categoryId)) {
      return true;
    }

    // Second try: look up category by ID and match by slug
    const site = api.container.lookup("service:site");
    if (site && site.categories) {
      const category = site.categories.find((c) => c.id === categoryId);
      if (category) {
        // Check if the category slug or name matches any setting
        const lowerSettings = categorySettings.map((s) => s.toLowerCase());
        if (lowerSettings.includes(category.slug?.toLowerCase()) ||
            lowerSettings.includes(category.name?.toLowerCase())) {
          return true;
        }

        // Also check parent category path (e.g., "products/1secure/ideas")
        if (category.slug) {
          const fullSlug = category.parentCategory
            ? `${category.parentCategory.slug}/${category.slug}`
            : category.slug;
          if (lowerSettings.includes(fullSlug.toLowerCase())) {
            return true;
          }
        }
      }
    }

    return false;
  };

  const castVote = async (topicId, source) => {
    if (!settings.auto_vote_enabled) {
      log("Auto-vote is disabled");
      return false;
    }

    if (autoVotedTopics.has(topicId)) {
      log("Already attempted auto-vote for topic:", topicId);
      return false;
    }

    autoVotedTopics.add(topicId);

    try {
      log(`Casting vote for topic ${topicId} (source: ${source})`);

      const response = await ajax("/voting/vote", {
        type: "POST",
        data: { topic_id: topicId },
      });

      log("Vote cast successfully for topic:", topicId, response);

      // Try multiple approaches to update the UI smoothly
      try {
        const topicController = api.container.lookup("controller:topic");
        const topic = topicController?.model;

        if (topic && topic.id === topicId) {
          // Update local state immediately for instant feedback
          topic.set("user_voted", true);
          topic.set("vote_count", (topic.vote_count || 0) + 1);
          log("Updated topic model properties");

          // Try appEvents to notify the voting plugin
          const appEvents = api.container.lookup("service:app-events");
          if (appEvents) {
            log("Triggering appEvents for vote update");
            appEvents.trigger("topic:voted", { topicId, voted: true });
            appEvents.trigger("topic-stats:update", { topicId });
          }

          // Give Ember a moment to process the property changes
          setTimeout(() => {
            // If the vote button still doesn't show as voted, try router refresh
            const router = api.container.lookup("service:router");
            if (router && router.refresh) {
              log("Refreshing route to ensure vote UI is updated");
              router.refresh();
            }
          }, 100);
        } else {
          // Fallback if topic model not found
          log("Topic model not found, reloading page");
          window.location.reload();
        }
      } catch (e) {
        log("Error updating UI, reloading page:", e);
        window.location.reload();
      }

      return true;
    } catch (error) {
      if (error.jqXHR?.status === 422) {
        log("Could not vote (already voted or voting not enabled):", topicId);
      } else {
        log("Error casting vote:", error.jqXHR?.status || error);
      }
      return false;
    }
  };

  // Auto-vote on page navigation to own topic
  // This reliably catches when the user is redirected to their newly created topic
  api.onPageChange((url) => {
    const topicMatch = url.match(/\/t\/[^/]+\/(\d+)/);
    if (!topicMatch) {
      return;
    }

    setTimeout(() => {
      const topicController = api.container.lookup("controller:topic");
      const topic = topicController?.model;

      if (!topic) {
        return;
      }

      if (
        topic.user_id === currentUser.id &&
        topic.can_vote &&
        !topic.user_voted &&
        isCategoryAllowed(topic.category_id)
      ) {
        log("Found unvoted own topic on page load:", topic.id);
        castVote(topic.id, "onPageChange");
      }
    }, 500);
  });
});
