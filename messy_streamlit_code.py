import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.graph_objects as go
import random

# Page configuration
st.set_page_config(
    page_title="HR1 Tax Impact Dashboard",
    page_icon="🏠",
    layout="wide"
)

# Load data
@st.cache_data
def load_data():
    return pd.read_csv("household_tax_income_changes.csv")

# Main app
def main():
    st.title("🏠 HR1 Tax Bill - Household Impact Dashboard")
    st.markdown("*Explore how the HR1 tax bill affects individual American households compared to current policy*")
    
    # Load the data
    df = load_data()
    
    # Sidebar for household selection
    st.sidebar.header("Select Household")
    
    # Initialize filtered dataframe
    df_filtered = df.copy()
    
    ### ALL FILTERS
    with st.sidebar.expander("🔍 Filters"):
        # Filter 1: Household Weight
        weight_options = {
            "All Households": 0,
            "Weight 1,000+": 1000,
            "Weight 5,000+": 5000,
            "Weight 10,000+": 10000,
            "Weight 25,000+": 25000,
            "Weight 50,000+": 50000
        }
        selected_weight = st.selectbox("Minimum Household Weight:", list(weight_options.keys()))  # Removed .sidebar
        min_weight = weight_options[selected_weight]
        if min_weight > 0:
            df_filtered = df_filtered[df_filtered['Household Weight'] >= min_weight]
        
        # Filter 2: Net Income
        income_ranges = {
            "All Income Levels": (0, float('inf')),
            "Under $25k": (0, 25000),
            "$25k - $50k": (25000, 50000),
            "$50k - $100k": (50000, 100000),
            "$100k - $200k": (100000, 200000),
            "$200k+": (200000, float('inf'))
        }
        selected_income = st.selectbox("Net Income:", list(income_ranges.keys()))  # Removed .sidebar
        min_income, max_income = income_ranges[selected_income]
        if min_income > 0 or max_income < float('inf'):
            df_filtered = df_filtered[
                (df_filtered['Baseline Net Income'] >= min_income) & 
                (df_filtered['Baseline Net Income'] <= max_income)
            ]
        
        # Filter 3: State
        states = ["All States"] + sorted(df['State'].unique().tolist())
        selected_state = st.selectbox("State:", states)  # Removed .sidebar
        if selected_state != "All States":
            df_filtered = df_filtered[df_filtered['State'] == selected_state]
        
        # Filter 4: Marital Status
        marital_options = ["All", "Married", "Single"]
        selected_marital = st.selectbox("Marital Status:", marital_options)  # Removed .sidebar
        if selected_marital != "All":
            is_married = selected_marital == "Married"
            df_filtered = df_filtered[df_filtered['Is Married'] == is_married]
        
        # Filter 5: Number of Dependents
        dependent_options = ["All", "0", "1", "2", "3+"]
        selected_dependents = st.selectbox("Number of Dependents:", dependent_options)  # Removed .sidebar
        if selected_dependents != "All":
            if selected_dependents == "3+":
                df_filtered = df_filtered[df_filtered['Number of Dependents'] >= 3]
            else:
                df_filtered = df_filtered[df_filtered['Number of Dependents'] == int(selected_dependents)]

        # Filter 6: Age of Head of Household
        age_ranges = {
            "All Ages": (0, 200),
            "Under 30": (0, 30),
            "30-40": (30, 40),
            "40-50": (40, 50),
            "50-60": (50, 60),
            "60-70": (60, 70),
            "70-80": (70, 80),
            "80+": (80, 200)
        }
        selected_age = st.selectbox("Head of Household Age:", list(age_ranges.keys()))
        min_age, max_age = age_ranges[selected_age]
        if selected_age != "All Ages":
            df_filtered = df_filtered[
                (df_filtered['Age of Head'] >= min_age) & 
                (df_filtered['Age of Head'] < max_age)
            ]
        
        # Show filter results  
        st.caption(f"📊 Showing {len(df_filtered):,} of {len(df):,} households")  # Removed .sidebar
        if len(df_filtered) == 0:
            st.error("No households match your filters!")  # Removed .sidebar
            st.stop()

    # Use df_filtered everywhere below this point

    
    selection_method = st.sidebar.radio(
        "Selection Method:",
        ["By Household ID", "Find Interesting Cases", "Random Shuffle"]
    )
    
    if selection_method == "By Household ID":
        household_id = st.sidebar.selectbox(
            "Choose Household ID:",
            df_filtered['Household ID'].unique()
        )
    
    elif selection_method == "Random Shuffle":
        if st.sidebar.button("🎲 Get Random Household"):
            # Store random selection in session state to persist across reruns
            st.session_state.random_household = df_filtered['Household ID'].sample(1).iloc[0]
        
        # Show the selected random household or pick initial one
        if 'random_household' not in st.session_state:
            st.session_state.random_household = df_filtered['Household ID'].sample(1).iloc[0]
        
        household_id = st.session_state.random_household
        st.sidebar.info(f"Random Household ID: {household_id}")
    else:
        # Pre-filter for interesting cases with top 20 rankings
        case_type = st.sidebar.selectbox("Select Case Type:", [
            "Largest % Federal Tax Increase",
            "Largest % Federal Tax Decrease", 
            "Largest Federal Tax Increase",
            "Largest Federal Tax Decrease",
            "Largest % Income Increase",
            "Largest % Income Decrease",
            "Largest Income Increase",
            "Largest Income Decrease"
        ])
        
        # Get top 20 households for selected category
        categories = {
            "Largest % Federal Tax Increase": ('nlargest', 'Percentage Change in Federal Tax Liability'),
            "Largest % Federal Tax Decrease": ('nsmallest', 'Percentage Change in Federal Tax Liability'),
            "Largest Federal Tax Increase": ('nlargest', 'Total Change in Federal Tax Liability'),
            "Largest Federal Tax Decrease": ('nsmallest', 'Total Change in Federal Tax Liability'),
            "Largest % Income Increase": ('nlargest', 'Percentage Change in Net Income'),
            "Largest % Income Decrease": ('nsmallest', 'Percentage Change in Net Income'),
            "Largest Income Increase": ('nlargest', 'Total Change in Net Income'),
            "Largest Income Decrease": ('nsmallest', 'Total Change in Net Income')
        }
        
        method, column = categories[case_type]
        top_households = getattr(df_filtered, method)(20, column)
                
        # Create ranked list for selection
        ranked_options = []
        household_ids = []  # Keep track of household IDs separately, sorry that this is not concise
        
        for i, (idx, row) in enumerate(top_households.iterrows(), 1):
            household_ids.append(row['Household ID'])  # Store the household ID
            
            if "%" in case_type:
                if "Tax" in case_type:
                    value = row['Percentage Change in Federal Tax Liability']
                    ranked_options.append(f"#{i}: {value:+.1f}%")
                else:  # Income
                    value = row['Percentage Change in Net Income']
                    ranked_options.append(f"#{i}: {value:+.1f}%")
            else:  # Dollar amounts
                if "Tax" in case_type:
                    value = row['Total Change in Federal Tax Liability']
                    ranked_options.append(f"#{i}: ${value:+,.0f}")
                else:  # Income
                    value = row['Total Change in Net Income']
                    ranked_options.append(f"#{i}: ${value:+,.0f}")
        
        # Let user select from ranked list
        selected_option = st.sidebar.selectbox(f"Top 20 for {case_type}:", ranked_options)
        
        # Get household ID using the index
        selected_index = ranked_options.index(selected_option)
        household_id = household_ids[selected_index]
        # Show it in a card
        st.sidebar.info(f"Selected Household ID: {household_id}")

    
    
    # Get household data
    household = df_filtered[df_filtered['Household ID'] == household_id].iloc[0]

    # Baseline Attributes in Sidebar
    st.sidebar.subheader("Baseline Household Attributes")
        
    st.sidebar.markdown(f"""
    **State:** {household['State']}  
    **Head of Household Age:** {household['Age of Head']:.0f} years  
    **Number of Dependents:** {household['Number of Dependents']:.0f}""")
    # Add children's ages if there are dependents
    if household['Number of Dependents'] > 0:
        dependent_ages = []
        for i in range(1, 12):  # Check dependents 1-11
            age_col = f'Age of Dependent {i}'
            if pd.notna(household[age_col]) and household[age_col] > 0:
                dependent_ages.append(f"{household[age_col]:.0f}")
        
        if dependent_ages:
            st.sidebar.markdown(f"**Children's Ages:** {', '.join(dependent_ages)} years")
    

    if household['Is Married']:
        st.sidebar.markdown(f"""**Marital Status:** Married  
    **Spouse Age:** {household['Age of Spouse']:.0f} years""")
    else:
        st.sidebar.markdown("**Marital Status:** Single")

    st.sidebar.markdown("**Income Sources:**")
    income_sources = [
        ("Employment Income", household['Employment Income']),
        ("Self-Employment Income", household['Self-Employment Income']),
        ("Tip Income", household['Tip Income']),
        ("Overtime Income", household['Overtime Income']),
        ("Capital Gains", household['Capital Gains'])
    ]

    for source, amount in income_sources:
        if amount > 0:
            st.sidebar.markdown(f"• {source}: ${amount:,.2f}")


    # Collapsible DF row
    with st.sidebar.expander("Full Dataframe Row"):
        # Get the row index (position in the CSV)
        row_index = df_filtered[df_filtered['Household ID'] == household_id].index[0]
        st.dataframe(household.to_frame().T, use_container_width=True)
        
    # Add separator and radio buttons
    st.sidebar.markdown("---")
    st.sidebar.subheader("Analysis Type")
    analysis_type = st.sidebar.radio(
        "Select what to analyze:",
        ["Federal Taxes", "Net Income"],
        index=0  # Default to Federal Taxes
    )
    
    # Display household information in cards
    col1, col2 = st.columns(2)
    
    with col1:
        # Baseline Calculated Values Card
        st.subheader("Baseline Federal Tax and Net Income")
        with st.container():
            st.metric(
                "Federal Tax Liability", 
                f"${household['Baseline Federal Tax Liability']:,.2f}"
            )
            st.metric(
                "Net Income", 
                f"${household['Baseline Net Income']:,.2f}"
            )
            
            # Show other current expenses
            if household['State Income Tax'] > 0:
                st.markdown(f"**State Income Tax:** ${household['State Income Tax']:,.2f}")    
            if household['Property Taxes'] > 0:
                st.markdown(f"**Property Taxes:** ${household['Property Taxes']:,.2f}")
      
    
    with col2:
        # Reform Impact Card
        st.subheader("🔄 HR1 Bill Impact Summary")
        with st.container():
            tax_change = household['Total Change in Federal Tax Liability']
            income_change = household['Total Change in Net Income']
            tax_pct_change = household['Percentage Change in Federal Tax Liability']
            income_pct_change = household['Percentage Change in Net Income']
            
            # Color coding for positive/negative changes
            tax_color = "red" if tax_change > 0 else "green"
            income_color = "green" if income_change > 0 else "red"
            
            st.markdown(f"""
            <div style="padding: 10px; border-radius: 5px; background-color: #f0f2f6;">
            <h4>Overall Impact</h4>
            <p style="color: {tax_color}; font-size: 18px; font-weight: bold;">
            Tax Change: ${tax_change:,.2f} ({tax_pct_change:+.1f}%)
            </p>
            <p style="color: {income_color}; font-size: 18px; font-weight: bold;">
            Net Income Change: ${income_change:,.2f} ({income_pct_change:+.1f}%)
            </p>
            </div>
            """, unsafe_allow_html=True)
        
        # Statistical Weight Card
        st.subheader("📈 Statistical Weight")
        with st.container():
            weight = household['Household Weight']
            st.metric("Population Weight", f"{math.ceil(weight):,}")
            st.caption("This household represents approximately this many similar households in the U.S.")
    
    # Create reform components data
    reform_components = [
        ("Tax Rate Reform", household['Change in Federal tax liability after Tax Rate Reform'], household['Change in Net income after Tax Rate Reform']),
        ("Standard Deduction Reform", household['Change in Federal tax liability after Standard Deduction Reform'], household['Change in Net income after Standard Deduction Reform']),
        ("Exemption Reform", household['Change in Federal tax liability after Exemption Reform'], household['Change in Net income after Exemption Reform']),
        ("Child Tax Credit Reform", household['Change in Federal tax liability after CTC Reform'], household['Change in Net income after CTC Reform']),
        ("QBID Reform", household['Change in Federal tax liability after QBID Reform'], household['Change in Net income after QBID Reform']),
        # Removed Estate Tax Reform, because it doesn't directly affect Federal Income Tax, like the other reforms.
        #("Estate Tax Reform", household['Federal tax liability after Estate Tax Reform'], household['Net income change after Estate Tax Reform']),
        ("AMT Reform", household['Change in Federal tax liability after AMT Reform'], household['Change in Net income after AMT Reform']),
        ("SALT Reform", household['Change in Federal tax liability after SALT Reform'], household['Change in Net income after SALT Reform']),
        ("Tip Income Exemption", household['Change in Federal tax liability after Tip Income Exempt'], household['Change in Net income after Tip Income Exempt']),
        ("Overtime Income Exemption", household['Change in Federal tax liability after Overtime Income Exempt'], household['Change in Net income after Overtime Income Exempt']),
        ("Auto Loan Interest Deduction", household['Change in Federal tax liability after Auto Loan Interest ALD'], household['Change in Net income after Auto Loan Interest ALD']),
        ("Miscellaneous Reform", household['Change in Federal tax liability after Miscellaneous Reform'], household['Change in Net income after Miscellaneous Reform']),
        ("Other Itemized Deductions Reform", household['Change in Federal tax liability after Other Itemized Deductions Reform'], household['Change in Net income after Other Itemized Deductions Reform']),
        ("Pease Reform", household['Change in Federal tax liability after Pease Reform'], household['Change in Net income after Pease Reform'])
    ]
    
    # Filter out components with no change
    active_components = [(name, tax_after, income_change) for name, tax_after, income_change in reform_components if abs(income_change) > 0.01]

    # Detailed Reform Breakdown
    st.subheader("🔍 Detailed Reform Component Analysis")
    
    if active_components:
        cols = st.columns(min(3, len(active_components)))
        for i, (name, tax_after, income_change) in enumerate(active_components):
            with cols[i % 3]:
                color = "green" if income_change > 0 else "red"
                st.markdown(f"""
                <div style="padding: 8px; border-radius: 5px; background-color: #f9f9f9; margin: 5px 0;">
                <h5>{name}</h5>
                <p style="color: {color}; font-weight: bold;">
                Net Income Change: ${income_change:,.2f} 
                </p>
                </div>
                """, unsafe_allow_html=True)
                
        # Waterfall Chart
        st.subheader("📊 Financial Impact Waterfall Chart")
        
        # Prepare data for waterfall chart
        baseline_tax = household['Baseline Federal Tax Liability']
        
        # Get tax liability changes (not net income changes)
        waterfall_data = []
        waterfall_data.append(("Baseline Federal Income Tax", baseline_tax, baseline_tax))
        
        running_total = baseline_tax
        
        for name, tax_after, income_change in active_components:
            # Calculate the tax change (negative income change = positive tax change)
            tax_change = -income_change
            running_total += tax_change
            waterfall_data.append((name, tax_change, running_total))
        
        # Final total
        final_tax = baseline_tax + household['Total Change in Federal Tax Liability']
        waterfall_data.append(("Final Federal Income Tax", final_tax, final_tax))
        
        # Create FEDERAL INCOME TAX waterfall chart (state option still needed, etc.)
        fig = go.Figure() 
        
        # Add baseline
        fig.add_trace(go.Waterfall(
            name="Federal Income Tax Impact",
            orientation="v",
            measure=["absolute"] + ["relative"] * len(active_components) + ["total"],
            x=[item[0] for item in waterfall_data],
            y=[item[1] for item in waterfall_data],
            text=[f"${item[1]:,.0f}" for item in waterfall_data],
            textposition="outside",
            connector={"line":{"color":"rgb(63, 63, 63)"}},
            increasing={"marker":{"color":"red"}},  # Tax increases in red
            decreasing={"marker":{"color":"green"}},  # Tax decreases in green
            totals={"marker":{"color":"blue"}}
        ))
        
        fig.update_layout(
            title=f"Federal Income Tax Liability Changes: ${baseline_tax:,.0f} → ${final_tax:,.0f}",
            xaxis_title="Reform Components",
            yaxis_title="Tax Liability ($)",
            showlegend=False,
            height=500,
            xaxis={'tickangle': -45}
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Verification
        total_calculated_change = sum([item[1] for item in waterfall_data[1:-1]])
        # Changed this from taxes, to overall change from all reforms!! Must change title accordingly
        # And negated the change in income so it would match the change in taxes
        actual_change = -household['Total Change in Net Income']

        # Check if calculated change is within $3 of other Tax Change calculation
        if abs(total_calculated_change - actual_change) < 3:
            pass
        else:
            st.error(f"Discrepancy detected: Calculated change ${total_calculated_change:,.2f} vs Actual change ${actual_change:,.2f}")

    else:
        st.info("This household is not significantly affected by any specific reform components.")
    
    # Summary for journalists
    st.subheader("📝 Story Summary")
    impact_level = "significantly" if abs(income_change) > 1000 else "moderately" if abs(income_change) > 100 else "minimally"
    direction = "benefits from" if income_change > 0 else "is burdened by"

    
    # Find the reform with the greatest absolute impact
    if active_components:
        biggest_impact_reform = max(active_components, key=lambda x: abs(x[2]))
        biggest_reform_name = biggest_impact_reform[0]
        biggest_reform_change = biggest_impact_reform[2]
        biggest_reform_text = f"The biggest change comes from the {biggest_reform_name} (${biggest_reform_change:+,.2f})."
    else:
        biggest_reform_text = "No single reform has a major impact."

    
    st.info(f"""
    **Quick Story Angle:** This {household['State']} household {impact_level} {direction} the HR1 bill, 
    with a net income change of {household['Total Change in Net Income']:,.2f} ({income_pct_change:+.1f}%). 
    {biggest_reform_text}
    The household represents approximately {f"{math.ceil(weight):,}"} similar American families.
    """)
    
if __name__ == "__main__":
    main()
