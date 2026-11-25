import { View, Text, StyleSheet } from 'react-native';

export default function UserHomeScreen() {
  return (
    <View style={styles.container}>
      <Text>User Home Screen</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
