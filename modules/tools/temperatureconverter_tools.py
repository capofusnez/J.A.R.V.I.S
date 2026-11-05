class TemperatureConverterTools:
    def run(self, text: str = "") -> str:
        if not text:
            return "No input provided"
        try:
            # Extract the temperature value and unit from the input string
            value, unit = text.split()
            value = float(value)
            if unit.upper() == 'F':
                # Convert Fahrenheit to Celsius
                celsius = (value - 32) * 5.0 / 9.0
                return f"{celsius:.2f} C"
            else:
                return "Unsupported unit. Please use 'F' for Fahrenheit."
        except ValueError:
            return "Invalid input format. Please provide a temperature value followed by the unit (e.g., '255 F')."