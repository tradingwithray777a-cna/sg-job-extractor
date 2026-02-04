PORTALS_ALL = [
    "MyCareersFuture",
    "Foundit",
    "FastJobs",
]

default_portals = [
    "MyCareersFuture",
    "FastJobs",
]

selected_portals = st.multiselect(
    "Select job portals to extract from",
    options=PORTALS_ALL,
    default=default_portals
)
