import { View, Text, StyleSheet } from 'react-native';

export default function AdminForgetPasswordScreen() {
  return (
    <View style={styles.container}>
      <Text>Admin Forget Password Screen</Text>
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