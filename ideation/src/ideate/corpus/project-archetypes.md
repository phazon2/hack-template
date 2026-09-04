---
title: Project archetypes and the twist that makes each specific
tags: archetype, chatbot, dashboard, marketplace, recommender, classifier, agent, clone, twist, novelty
kind: archetype
---

# Project archetypes and the twist that makes each specific

Almost every hackathon project is an instance of one of seven archetypes. Judges know
the archetypes and have seen dozens of each. An archetype is not a bad starting point;
it is a bad ending point. This file explains why each one reads as generic and the
concrete twist that makes it read as specific. When an idea is an archetype without a
twist, the ideation step should either add the twist or drop the idea.

## Assistant or chatbot

Why it reads as generic: a chat box over a prompt and some documents is the default
LLM project. Judges have seen a chatbot for legal documents, for onboarding, for
course material and for customer support all in one afternoon. The chat interface
hides the work, so the demo is a person typing and waiting. The twist that makes it
specific: remove the chat box. Make the assistant act on a specific artefact in a
specific moment: it fills the form the nurse is staring at, it annotates the pull
request as it is opened, it rewrites the shift roster when someone calls in sick. The
demo shows the artefact changing, not text scrolling. Add citations to real sources
the judge can click, and one guardrail that visibly fires.

## Dashboard

Why it reads as generic: charts over a dataset the team found that morning. Dashboards
display; they do not decide, and judges cannot tell from a dashboard whether the team
understood the data. The twist: turn one chart into an alert with a recommended
action for a named role. "Here is the ward's bed occupancy" is a dashboard; "the charge
nurse gets a message at 6am saying two discharges will free beds by noon, approve or
override" is a product. Show the trigger firing during the demo, ideally from a live
feed that changed during the event.

## Marketplace

Why it reads as generic: two-sided platforms need both sides to exist, which a
hackathon cannot show, so the demo is empty listings and a signup form. Judges know the
hard part of a marketplace is liquidity and that no team solved it in a day. The twist:
pick one side and one transaction and make it work end to end for a real, tiny
population. A marketplace for one street, one building, one classroom, seeded with
real public data on one side (open listings, public events, transit) so the demo has
content on day one. Show the matching logic doing something a notice board cannot.

## Recommender

Why it reads as generic: "we recommend X based on your preferences" is a solved
pattern and the demo needs a user history the judge does not have. Cold start kills
the demo. The twist: recommend from context the judge can see rather than from a
profile: the weather right now, the exhibition the museum has open this week, what is
in this photo of a fridge. Make the recommendation explain itself in one line with the
evidence, and let the judge change the input and watch the recommendation change.

## Classifier

Why it reads as generic: training a model on a downloaded dataset and showing an
accuracy number is a course assignment, not a product. Judges cannot verify the
number and the demo is a file upload. The twist: put the classifier inside a workflow
where the classification triggers an action for a named user, and demo on an input
the judge chooses from a small live set. A classifier that routes a photographed
receipt into the right expense category and files it is specific; a classifier with
a confusion matrix is not. Show what happens on a low-confidence input.

## Automation agent

Why it reads as generic: "an agent that does your tasks" is unbounded, so the demo is
either a toy or a spinner that eventually produces text. Judges have watched many
agents fail to finish. The twist: bound the agent to one workflow with three to five
tools, at least one of which acts on the world visibly (a row appears, a message
sends, a file is written), and show the tool-call trace as it happens. Include the
step where the agent asks for confirmation or declines because the evidence is missing.
The trace and the guardrail are the demo.

## "X for Y" clone

Why it reads as generic: "Uber for dog walkers", "Duolingo for tax law", "Tinder for
co-founders" borrow a known product's shape and change the noun. Judges hear the
formula and assume the team has not looked at what makes Y different. The twist:
identify the one thing about Y that breaks the original product's core assumption,
and build only that. If Y's users have no smartphone, the product is voice or SMS; if
Y's transactions are once a year, the loop is not daily engagement but a single
well-timed reminder. Name the original product openly and say precisely what is
different and why it matters for the named user.

## Combining archetypes is not a twist

A chatbot on top of a dashboard is still generic. A marketplace with a recommender is
still generic. Stacking archetypes adds scope without adding specificity. The twist
always comes from the user and the moment: who, doing what, at what time, and what
changes on screen when the product works. Two archetypes with no named user lose to
one archetype with a named nurse at 6am.

## How to use this file during ideation

For each candidate idea, name its archetype in one word. Then write the twist in one
sentence using the pattern for that archetype: which artefact the assistant changes,
which alert the dashboard fires, which single transaction the marketplace completes,
which visible context the recommender uses, which action the classifier triggers,
which tool call the agent makes on the world, which broken assumption the clone
addresses. If the twist sentence cannot be written, the idea is not ready to build.
