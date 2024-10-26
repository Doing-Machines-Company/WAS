from utils.trajectory_saves import *
import pickle


with open('saved_trajectories/First a large meatzza, then a medium meatzza, then another medium meatzza, and finally a pepperoni._20241026_1854.pkl', 'rb') as file:
    loaded_instance = pickle.load(file)

loaded_instance.step_through()