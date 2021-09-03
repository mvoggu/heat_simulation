import streamlit as st
import pandas as pd
import math
import base64

STEFAN_BOLTZMANN_CONSTANT = 5.67 * 10**-8

# hide Hamburger menu and "Made with Streamlit" footer
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

def df_to_link(df, title='Download csv', filename='download.csv'):
    """Generates a link allowing the data in a given pandas dataframe to be downloaded.
    input:  dataframe
    output: href string
    """
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()  # some strings <-> bytes conversions necessary here
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}">{title}</a>'

class Kiln():
    def __init__(self, diameter, ambient_velocity, ambient_temp, temp_unit, emissivity, interval, df):
        self.diameter = diameter # meter
        self.ambient_velocity = ambient_velocity # m/s
        self.ambient_temp = ambient_temp if temp_unit=='Kelvin' else ambient_temp + 273 # Kelvin
        self.emissivity = emissivity
        self.interval = interval # meter
        self.section_area = math.pi * diameter * interval

        # auto-generate names for columns in input excel
        columns_count = len(df.columns)
        df.columns = [f'input {i}' for i in range(1, columns_count+1)]
        
        # compute average of temperatures in input columns
        average = df[list(df.columns)].sum(axis=1)/columns_count
        df['temp'] = average if temp_unit=='Kelvin' else average + 273

        # auto-generate lengths at which readings were taken based on interval and number of readings
        rows_count = len(df.index)
        length = [i for i in range(interval, interval*rows_count+1, interval)]
        df.insert(0, 'length', length)

        self.df = df # Pandas DF with temp readings in Kelvin

    def radiation(self, tempcol='temp'):
        """Calculate radiation heat loss (kcal/hr) from each section of kiln"""
        return self.emissivity * self.section_area * STEFAN_BOLTZMANN_CONSTANT * (self.df[tempcol]**4 - self.ambient_temp**4)

    def convection(self, tempcol='temp'):
        """ Calculate convection heat loss (kcal/hr) from each section of kiln """
        if self.ambient_velocity < 3:
            # Natural Convection
            return 80.33 * (((self.df[tempcol] + self.ambient_temp)/2)**-0.724 * (self.df[tempcol] - self.ambient_temp)**1.333) * self.section_area
        else:
            # Forced Convection
            return 28.03 * (self.df[tempcol] * self.ambient_temp)**-0.351 * self.ambient_velocity**0.805 * self.diameter**-0.195 * (self.df[tempcol] - self.ambient_temp) * self.section_area

# input values using streamlit web interface
diameter = st.sidebar.number_input('Kiln diameter(m)', 0.01, 100.0, 4.75)
clinker_production = st.sidebar.number_input('Clinker production(kg/hr)', 0.01, 100000000.0, 290000.0, 1000.0) # kg/hr
ambient_velocity = st.sidebar.number_input('Ambient velocity', 0.0, 100.0)
ambient_temp = st.sidebar.number_input('Ambient temperature', 0.0, 373.0, 29.0)
temp_unit = st.sidebar.selectbox('Unit', ('Celsius', 'Kelvin'))
emissivity = st.sidebar.slider('emissivity', 0.0, 1.0, 0.77)
interval = st.sidebar.slider('interval', 1, 10, 1)
input_excel = st.file_uploader('Upload excel', type=['xls','xlsx','xlsm','xlsb','odf'])
st.sidebar.subheader('Notes:')
st.sidebar.info("First meter starts from kiln outlet side")
st.sidebar.info("\"interval\" is the distance between consecutive temperature readings. For example, when surface temperature was measured every 2 meters, interval would be 2")
st.sidebar.info("Multiple temperature readings can be provided at each point by putting them in separate excel columns. In such case, average of the readings will automatically be computed and used")
st.sidebar.info("Fill columns in input Excel starting from column A and use columns B,C,D,... as required. Columns should contain only the temperature readings in numbers and nothing else, not even column headers")

if input_excel is not None:
    df = pd.read_excel(input_excel, header=None)
    kiln = Kiln(diameter, ambient_velocity, ambient_temp, temp_unit, emissivity, interval, df)
    
    # compute & plot data
    kiln.df['radiation'] = kiln.radiation()/clinker_production
    kiln.df['convection'] = kiln.convection()/clinker_production
    kiln.df['total loss'] = kiln.df['radiation'] + kiln.df['convection']
    st.write(kiln.df.style.background_gradient(cmap='hot_r'))
    df.plot.scatter('length', 'length',c = 'total loss', cmap='hot_r', colorbar=True, title='Colored kiln')
    st.pyplot()
    df.plot.scatter('length', 'total loss',c = 'total loss', cmap='hot_r', colorbar=True, title='Heat loss along kiln length')
    st.pyplot()
    total_loss = df['total loss'].sum()
    st.subheader(f'Total heat loss = {total_loss:.2f} KCal per Kg clinker')

    # make a copy of dataframe till here
    df_copy = df.copy()
    
    # find outliers
    Q1 = df['total loss'].quantile(0.25)
    Q3 = df['total loss'].quantile(0.75)
    IQR = Q3 - Q1
    upper_whisker = Q3 + 1.5 * IQR
    lower_whisker = Q1 - 1.5 * IQR
    st.subheader('High outliers:')
    st.write(df[df['total loss'] > upper_whisker].style.hide_index())
    st.subheader('Low outliers:')
    st.write(df[df['total loss'] < lower_whisker].style.hide_index())
    high_outliers = []
    low_outliers = []
    for index,loss in df['total loss'].iteritems():
        if loss > upper_whisker:
            high_outliers.append(index)
        if loss < lower_whisker:
            low_outliers.append(index)
    
    if len(high_outliers) > 0:
        # median of temperatures which do not correspond to outliers
        mediantemp = df['temp'].drop(high_outliers).drop(low_outliers).median()
        df['new temp'] = df['temp']
        # replace temperatures corresponding to high outliers with above computed median
        for index in high_outliers:
            df.loc[index,'new temp'] = mediantemp

        # recompute and plot data
        st.subheader('After repairs:')
        df['new radiation'] = kiln.radiation('new temp')/clinker_production
        df['new convection'] = kiln.convection('new temp')/clinker_production
        df['new total loss'] = df['new radiation'] + df['new convection']
        st.write(kiln.df.style.background_gradient(cmap='hot_r'))
        df.plot.scatter('length', 'length',c = 'new total loss', cmap='hot_r', colorbar=True, title='Colored kiln after repairs')
        st.pyplot()
        df.plot.scatter('length', 'new total loss',c = 'new total loss', cmap='hot_r', colorbar=True, title='Heat loss along kiln length after repairs')
        st.pyplot()
        new_total_loss = df['new total loss'].sum()
        st.subheader(f'Total heat loss after removing high outliers= {new_total_loss:.2f} KCal per Kg clinker')

        savings = total_loss - new_total_loss
        if savings > 0.0:
            # compute savings per year due to repairs
            savings_per_hour = savings * clinker_production
            WORKING_DAYS_PER_YEAR = 330
            working_hours_per_year = WORKING_DAYS_PER_YEAR * 24
            savings_per_year = savings_per_hour * working_hours_per_year
            COAL_CALORIFIC_VALUE = 4500 # kcal/Kg
            coal_saved_per_year = savings_per_year / COAL_CALORIFIC_VALUE
            coal_saved_per_year_tons = coal_saved_per_year/1000
            COAL_COST_PER_TON = 4500 # rupees
            money_saved_per_year = coal_saved_per_year_tons * COAL_COST_PER_TON

            # compute repair costs
            kiln_length_damaged = len(high_outliers)
            RINGS_PER_METER = 5
            SHELL_THICKNESS = 16 # mm
            BRICK_HEIGHT = 220 # mm
            BRICK_COST = 100
            internal_diameter = kiln.diameter * 1000 - 2 * SHELL_THICKNESS # mm
            bricks_per_ring = math.floor(3.14*(internal_diameter - BRICK_HEIGHT)/71.5)
            bricks_per_meter = bricks_per_ring * RINGS_PER_METER
            bricks_damaged_count = bricks_per_meter * kiln_length_damaged
            repair_cost = bricks_damaged_count * BRICK_COST
            
            # compute net savings
            savings_per_year_rupees = money_saved_per_year - repair_cost

            # print summary
            st.header('Summary:')
            st.subheader(f'Total heat loss = {total_loss:.2f} KCal per Kg clinker')
            if len(low_outliers) > 0:
                low_outliers_text = ''.join([f'{x+1}m ' for x in low_outliers])
                st.subheader(f'Coating formation suspected at:')
                st.write(low_outliers_text)
            else:
                st.subheader(f'No Coating formation suspected')            
            high_outliers_text = ''.join([f'{x+1}m ' for x in high_outliers])
            st.subheader(f'{kiln_length_damaged} meters of kiln was found to be damaged at:')
            st.write(high_outliers_text)
            st.subheader('On repairing:')
            st.subheader(f'About {savings:.2f} KCal can be saved for each Kg clinker produced')
            st.subheader(f'{savings_per_year_rupees/10**5:.2f} lakh rupees can be saved per year')
        else:
            # high outliers are replaced but savings are not positive
            # This is not supposed to happen
            st.subheader(f'Total heat loss after removing high outliers seems to be more than earlier. Something is wrong...')
    else:
        # print summary
        st.header('Summary:')
        st.subheader(f'Total heat loss = {total_loss:.2f} KCal per Kg clinker')
        st.subheader('No high outliers found')
        if len(low_outliers) > 0:
            low_outliers_text = ''.join([f'{x+1}m ' for x in low_outliers])
            st.subheader(f'Coating formation suspected at:')
            st.write(low_outliers_text)
        else:
            st.subheader(f'No Coating formation suspected')

    # download heat loss calculations as csv
    download_link = df_to_link(df_copy, title='Download calculations', filename='calculations.csv')
    st.markdown(download_link, unsafe_allow_html=True)